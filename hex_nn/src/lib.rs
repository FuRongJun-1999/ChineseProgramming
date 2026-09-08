//! hex_nn · 蜂窝 CNN 核心算子与信息差门控训练步(Rust 性能后端)
//! ====================================================================
//! 语义源:AEIS/aeis/hex_train.py(hex_conv_batch/train_infogap)+
//!        hex_hier.py(HexHierNet 两层堆叠前向)。
//! 纪律:
//!   - 零链式法则:有限差分符号更新(荣反传语义:子部分计算单元对
//!     预测信息差的调整;死区 |g|<1e-6 支路冻结;递归收敛);
//!   - 随机决策由外部 plan 预生成(每步 batch 索引+支路采样索引)——
//!     本 crate 是确定性执行器,同 plan 必须逐位复现 D 曲线;
//!   - 求和顺序与 Python 参考实现一致(双后端等价,容差 1e-9)。

/// 错行六邻偏移(与 Python hex_conv_batch 严格一致):
/// 偶数行/奇数行的六邻 (dq, dr)。
const EVEN_OFF: [(i64, i64); 6] = [(-1, 0), (1, 0), (-1, -1), (0, -1), (-1, 1), (0, 1)];
const ODD_OFF: [(i64, i64); 6] = [(-1, 0), (1, 0), (0, -1), (1, -1), (0, 1), (1, 1)];

/// 蜂窝卷积(批量)。
/// f: (B, r, c, C) 行主序;k: (C, 7) 逐通道核([自身,E,NE,NW,W,SW,SE])。
/// 边界:replicate(出界邻取自身)。奇/偶行直接分支(与 Python 的
/// rowmask 数学等价:e + mask*(o-e) = 奇行取 o、偶行取 e)。
pub fn hex_conv_batch(f: &[f64], b: usize, r: usize, c: usize, ch: usize,
                      k: &[f64]) -> Vec<f64> {
    let mut out = vec![0.0f64; b * r * c * ch];
    let idx = |bb: usize, rr: i64, cc: i64, chh: usize| -> usize {
        let rc = rr.clamp(0, r as i64 - 1) as usize;
        let cc2 = cc.clamp(0, c as i64 - 1) as usize;
        ((bb * r + rc) * c + cc2) * ch + chh
    };
    for bb in 0..b {
        for rr in 0..r {
            let odd = (rr % 2) == 1;
            let offs = if odd { ODD_OFF } else { EVEN_OFF };
            for cc in 0..c {
                for chh in 0..ch {
                    let mut acc = k[chh * 7] * f[idx(bb, rr as i64, cc as i64, chh)];
                    for (i, (dq, dr)) in offs.iter().enumerate() {
                        acc += k[chh * 7 + 1 + i]
                            * f[idx(bb, rr as i64 + dr, cc as i64 + dq, chh)];
                    }
                    out[idx(bb, rr as i64, cc as i64, chh)] = acc;
                }
            }
        }
    }
    out
}

fn lrelu(v: f64, a: f64) -> f64 {
    if v > 0.0 { v } else { a * v }
}

/// HexHierNet 堆叠前向(语义 = hex_hier.HexHierNet._h1/l2_features/l3_logits)。
/// lat: (B,r,c,3);conv1: (K1,7)(每核跨 RGB 复制后求和);
/// conv2: (K2,K1,7);head: (9, K2+3)。
/// 返回 (logits (B,9), deep_feat (B,K2), colorfeat (B,3))。
pub fn forward(lat: &[f64], b: usize, r: usize, c: usize,
               conv1: &[f64], k1: usize,
               conv2: &[f64], k2: usize,
               head: &[f64]) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let ch = 3usize;
    // L1:每核 conv(3 通道同核)→跨通道求和→leaky → (B,r,c,K1)
    let mut h1 = vec![0.0f64; b * r * c * k1];
    let mut kern3 = vec![0.0f64; ch * 7];
    for kk in 0..k1 {
        for chh in 0..ch {
            for j in 0..7 {
                kern3[chh * 7 + j] = conv1[kk * 7 + j];
            }
        }
        let out = hex_conv_batch(lat, b, r, c, ch, &kern3);
        for i in 0..(b * r * c) {
            let s: f64 = (0..ch).map(|chh| out[i * ch + chh]).sum();
            h1[i * k1 + kk] = lrelu(s, 0.05);
        }
    }
    // L1.5:每核 conv2[k] (K1,7) 作用于 h1 →跨通道求和→leaky → (B,r,c,K2)
    let mut h2 = vec![0.0f64; b * r * c * k2];
    for kk in 0..k2 {
        let kern = &conv2[kk * k1 * 7..(kk + 1) * k1 * 7];
        let out = hex_conv_batch(&h1, b, r, c, k1, kern);
        for i in 0..(b * r * c) {
            let s: f64 = (0..k1).map(|chh| out[i * k1 + chh]).sum();
            h2[i * k2 + kk] = lrelu(s, 0.05);
        }
    }
    // RMS 空间池化 → deep (B,K2);colorfeat = lat 全局均值 (B,3)
    let npix = r * c;
    let mut deep = vec![0.0f64; b * k2];
    for bb in 0..b {
        for kk in 0..k2 {
            let mut s = 0.0f64;
            for i in 0..npix {
                let v = h2[(bb * npix + i) * k2 + kk];
                s += v * v;
            }
            deep[bb * k2 + kk] = (s / npix as f64 + 1e-12).sqrt();
        }
    }
    let mut color = vec![0.0f64; b * 3];
    for bb in 0..b {
        for chh in 0..3 {
            let mut s = 0.0f64;
            for i in 0..npix {
                s += lat[(bb * npix + i) * 3 + chh];
            }
            color[bb * 3 + chh] = s / npix as f64;
        }
    }
    // logits = feat @ head.T;feat = [deep, color]
    let fin = k2 + 3;
    let mut logits = vec![0.0f64; b * 9];
    for bb in 0..b {
        for o in 0..9 {
            let mut s = 0.0f64;
            for j in 0..k2 {
                s += deep[bb * k2 + j] * head[o * fin + j];
            }
            for j in 0..3 {
                s += color[bb * 3 + j] * head[o * fin + k2 + j];
            }
            logits[bb * 9 + o] = s;
        }
    }
    (logits, deep, color)
}

/// 联合信息差(hex_hier.train_hier.joint_loss):
/// D = CE(obj) + 0.5·CE(shape 边缘化)。OBJ 顺序 shape|color,
/// shape s 的类 = {3s, 3s+1, 3s+2}。
pub fn joint_loss(lat: &[f64], b: usize, r: usize, c: usize,
                  conv1: &[f64], k1: usize, conv2: &[f64], k2: usize,
                  head: &[f64], obj_idx: &[usize], shape_idx: &[usize]) -> f64 {
    let (logits, _, _) = forward(lat, b, r, c, conv1, k1, conv2, k2, head);
    let mut d_obj = 0.0f64;
    let mut d_shape = 0.0f64;
    for bb in 0..b {
        let mut zmax = f64::NEG_INFINITY;
        for o in 0..9 {
            zmax = zmax.max(logits[bb * 9 + o]);
        }
        let mut z: Vec<f64> = (0..9)
            .map(|o| (logits[bb * 9 + o] - zmax).exp())
            .collect();
        let zsum: f64 = z.iter().sum();
        for v in z.iter_mut() {
            *v /= zsum;
        }
        // 统一 -log(p + 1e-12)(与 Python 参考实现一致)
        d_obj -= (z[bb * 0 + obj_idx[bb]] + 1e-12).ln();
        let mut ps = 0.0f64;
        for j in 0..3 {
            ps += z[shape_idx[bb] * 3 + j];
        }
        d_shape -= (ps + 1e-12).ln();
    }
    d_obj / b as f64 + 0.5 * d_shape / b as f64
}

/// 区域 loss:weights 显式传参(修复闭包捕获 vec 导致扰动不可见的 bug)。
fn loss_sel(weights: &[f64], sel: &[usize], lat: &[f64], r: usize, c: usize,
            obj_idx: &[usize], shape_idx: &[usize], k1: usize, k2: usize) -> f64 {
    let mut xs = Vec::with_capacity(sel.len() * r * c * 3);
    let mut ss = Vec::with_capacity(sel.len());
    let mut oo = Vec::with_capacity(sel.len());
    for &i in sel {
        xs.extend_from_slice(&lat[i * r * c * 3..(i + 1) * r * c * 3]);
        ss.push(shape_idx[i]);
        oo.push(obj_idx[i]);
    }
    joint_loss(&xs, sel.len(), r, c, &weights[0..k1 * 7], k1,
               &weights[k1 * 7..k1 * 7 + k2 * k1 * 7], k2,
               &weights[k1 * 7 + k2 * k1 * 7..], &oo, &ss)
}

/// 训练计划的一步(有限差分符号更新,零链式法则):
/// 对 plan 指定的每个支路:±eps 前向 → g=(dp-dm)/2eps →
/// |g|<deadzone 冻结,否则 v[pi] -= lr·sign(g)(坐标下降:
/// 后续支路基于已更新向量——与 Python 严格一致)。
pub fn train_steps(
    lat: &[f64], _n: usize, r: usize, c: usize,
    obj_idx: &[usize], shape_idx: &[usize],
    plan_batch: &[Vec<usize>], plan_sample: &[Vec<usize>],
    lr: f64, eps: f64, deadzone: f64,
    vec: &mut Vec<f64>, k1: usize, k2: usize,
) -> Vec<f64> {
    let mut curve = Vec::with_capacity(plan_batch.len());
    for (step, bidx) in plan_batch.iter().enumerate() {
        let d = loss_sel(vec, bidx, lat, r, c, obj_idx, shape_idx, k1, k2);
        curve.push(d);
        let sample = &plan_sample[step];
        let mut v = vec.clone();
        for &pi in sample.iter() {
            let old = v[pi];
            v[pi] = old + eps;
            let dp = loss_sel(&v, bidx, lat, r, c, obj_idx, shape_idx, k1, k2);
            v[pi] = old - eps;
            let dm = loss_sel(&v, bidx, lat, r, c, obj_idx, shape_idx, k1, k2);
            v[pi] = old;
            let g = (dp - dm) / (2.0 * eps);
            if g.abs() >= deadzone {
                v[pi] = old - lr * g.signum();
            }
        }
        vec.copy_from_slice(&v);
    }
    curve
}

// ==================== R2 · 支路级并行(批量评估-收敛) ====================

/// 并行训练步(语义升级,第四篇「认知结构并行」的直接实现):
/// 每步先取步初快照 v;64 个支路的有限差分**彼此独立、并行评估**
/// (rayon,每支路只读快照+私有 3KB 拷贝,无锁),全部完成后
/// **统一收敛**(按采样顺序应用更新——不同支路不同参数位,幂等无冲突)。
/// 与串行坐标下降的差异:支路梯度基于步初快照而非「已更新向量」——
/// 并行评估-收敛语义,行为相当性由 D 曲线对照验证,逐位等价由
/// py_executor_par(同语义 Python 参考)验收。
pub fn train_steps_par(
    lat: &[f64], r: usize, c: usize,
    obj_idx: &[usize], shape_idx: &[usize],
    plan_batch: &[Vec<usize>], plan_sample: &[Vec<usize>],
    lr: f64, eps: f64, deadzone: f64,
    vec: &mut Vec<f64>, k1: usize, k2: usize,
) -> Vec<f64> {
    use rayon::prelude::*;
    let mut curve = Vec::with_capacity(plan_batch.len());
    for (step, bidx) in plan_batch.iter().enumerate() {
        let d = loss_sel(vec, bidx, lat, r, c, obj_idx, shape_idx, k1, k2);
        curve.push(d);
        let v = vec.clone();                       // 步初快照(只读共享)
        let sample = &plan_sample[step];
        // 并行评估:每支路独立 (pi, 接受?, 增量)
        let updates: Vec<(usize, bool, f64)> = sample
            .par_iter()
            .map(|&pi| {
                let old = v[pi];
                let mut vp = v.clone();
                vp[pi] = old + eps;
                let dp = loss_sel(&vp, bidx, lat, r, c, obj_idx, shape_idx, k1, k2);
                let mut vm = v.clone();
                vm[pi] = old - eps;
                let dm = loss_sel(&vm, bidx, lat, r, c, obj_idx, shape_idx, k1, k2);
                let g = (dp - dm) / (2.0 * eps);
                (pi, g.abs() >= deadzone, -lr * g.signum())
            })
            .collect();
        // 统一收敛(串行应用,顺序=采样顺序)
        for (pi, ok, delta) in updates {
            if ok {
                vec[pi] += delta;
            }
        }
    }
    curve
}

/// plan 文件格式(二进制,小端):///   magic u64 = 0x4845584E4E525531 ("HEXNNRU1")
///   steps u64, batch_size u64, sample_size u64
///   steps × (batch_size × u32) ++ steps × (sample_size × u32)
pub fn parse_plan(bytes: &[u8]) -> Result<(Vec<Vec<usize>>, Vec<Vec<usize>>), String> {
    let rd_u64 = |o: usize| -> u64 {
        u64::from_le_bytes(bytes[o..o + 8].try_into().unwrap())
    };
    let magic = rd_u64(0);
    if magic != 0x4845584E4E525531 {
        return Err("bad magic".into());
    }
    let steps = rd_u64(8) as usize;
    let bs = rd_u64(16) as usize;
    let ss = rd_u64(24) as usize;
    let mut o = 32usize;
    let mut pb = Vec::with_capacity(steps);
    let mut ps = Vec::with_capacity(steps);
    for _ in 0..steps {
        let mut v = Vec::with_capacity(bs);
        for _ in 0..bs {
            v.push(u32::from_le_bytes(bytes[o..o + 4].try_into().unwrap()) as usize);
            o += 4;
        }
        pb.push(v);
    }
    for _ in 0..steps {
        let mut v = Vec::with_capacity(ss);
        for _ in 0..ss {
            v.push(u32::from_le_bytes(bytes[o..o + 4].try_into().unwrap()) as usize);
            o += 4;
        }
        ps.push(v);
    }
    Ok((pb, ps))
}


// ==================== 三层前端(M4.13 · conv3 可学习) ====================

/// 三层堆叠前向:conv1(K1,7)→conv2(K2,K1,7)→conv3(K3,K2,7)→head(9,K3+3)。
/// 返回 (logits (B,9), deep3 (B,K3), color (B,3))。
pub fn forward3(lat: &[f64], b: usize, r: usize, c: usize,
                conv1: &[f64], k1: usize,
                conv2: &[f64], k2: usize,
                conv3: &[f64], k3: usize,
                head: &[f64]) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let ch = 3usize;
    let mut kern3 = vec![0.0f64; ch * 7];
    let mut h1 = vec![0.0f64; b * r * c * k1];
    for kk in 0..k1 {
        for chh in 0..ch {
            for j in 0..7 {
                kern3[chh * 7 + j] = conv1[kk * 7 + j];
            }
        }
        let out = hex_conv_batch(lat, b, r, c, ch, &kern3);
        for i in 0..(b * r * c) {
            let s: f64 = (0..ch).map(|chh| out[i * ch + chh]).sum();
            h1[i * k1 + kk] = lrelu(s, 0.05);
        }
    }
    let mut h2 = vec![0.0f64; b * r * c * k2];
    for kk in 0..k2 {
        let out = hex_conv_batch(&h1, b, r, c, k1, &conv2[kk * k1 * 7..(kk + 1) * k1 * 7]);
        for i in 0..(b * r * c) {
            let s: f64 = (0..k1).map(|chh| out[i * k1 + chh]).sum();
            h2[i * k2 + kk] = lrelu(s, 0.05);
        }
    }
    let mut h3 = vec![0.0f64; b * r * c * k3];
    for kk in 0..k3 {
        let out = hex_conv_batch(&h2, b, r, c, k2, &conv3[kk * k2 * 7..(kk + 1) * k2 * 7]);
        for i in 0..(b * r * c) {
            let s: f64 = (0..k2).map(|chh| out[i * k2 + chh]).sum();
            h3[i * k3 + kk] = lrelu(s, 0.05);
        }
    }
    let npix = r * c;
    let mut deep = vec![0.0f64; b * k3];
    for bb in 0..b {
        for kk in 0..k3 {
            let mut s = 0.0f64;
            for i in 0..npix {
                let v = h3[(bb * npix + i) * k3 + kk];
                s += v * v;
            }
            deep[bb * k3 + kk] = (s / npix as f64 + 1e-12).sqrt();
        }
    }
    let mut color = vec![0.0f64; b * 3];
    for bb in 0..b {
        for chh in 0..3 {
            let mut s = 0.0f64;
            for i in 0..npix {
                s += lat[(bb * npix + i) * 3 + chh];
            }
            color[bb * 3 + chh] = s / npix as f64;
        }
    }
    let fin = k3 + 3;
    let mut logits = vec![0.0f64; b * 9];
    for bb in 0..b {
        for oo in 0..9 {
            let mut acc = 0.0f64;
            for j in 0..k3 {
                acc += deep[bb * k3 + j] * head[oo * fin + j];
            }
            for j in 0..3 {
                acc += color[bb * 3 + j] * head[oo * fin + k3 + j];
            }
            logits[bb * 9 + oo] = acc;
        }
    }
    (logits, deep, color)
}

/// 三层联合损失(w=完整参数向量)。
pub fn joint_loss3(lat: &[f64], sel: &[usize], lat_all: &[f64], r: usize, c: usize,
                   obj_idx: &[usize], shape_idx: &[usize],
                   w: &[f64], k1: usize, k2: usize, k3: usize) -> f64 {
    let c1e = k1 * 7;
    let c2e = c1e + k2 * k1 * 7;
    let c3e = c2e + k3 * k2 * k1 * 7;
    let mut xs = Vec::with_capacity(sel.len() * r * c * 3);
    let mut oo = Vec::with_capacity(sel.len());
    let mut ss = Vec::with_capacity(sel.len());
    for &i in sel {
        xs.extend_from_slice(&lat_all[i * r * c * 3..(i + 1) * r * c * 3]);
        oo.push(obj_idx[i]);
        ss.push(shape_idx[i]);
    }
    let b = sel.len();
    let c1e = k1 * 7;
    let c2e = c1e + k2 * k1 * 7;
    let c3e = c2e + k3 * k2 * 7;          // conv3 每核 (K2,7):k3*k2*7
    let (logits, _, _) = forward3(&xs, b, r, c,
        &w[0..c1e], k1, &w[c1e..c2e], k2, &w[c2e..c3e], k3, &w[c3e..]);
    let mut d_obj = 0.0f64;
    let mut d_shape = 0.0f64;
    for bb in 0..b {
        let mut zmax = f64::NEG_INFINITY;
        for o in 0..9 { zmax = zmax.max(logits[bb * 9 + o]); }
        let mut z: Vec<f64> = (0..9).map(|o| (logits[bb * 9 + o] - zmax).exp()).collect();
        let zs: f64 = z.iter().sum();
        for v in z.iter_mut() { *v /= zs; }
        d_obj -= (z[oo[bb]] + 1e-12).ln();
        let mut ps = 0.0f64;
        for j in 0..3 { ps += z[ss[bb] * 3 + j]; }
        d_shape -= (ps + 1e-12).ln();
    }
    d_obj / b as f64 + 0.5 * d_shape / b as f64
}

/// 三层训练步(批量评估-收敛,rayon 并行,同 train_steps_par 语义)。
pub fn train3_steps_par(
    lat_all: &[f64], r: usize, c: usize,
    obj_idx: &[usize], shape_idx: &[usize],
    plan_batch: &[Vec<usize>], plan_sample: &[Vec<usize>],
    lr: f64, eps: f64, deadzone: f64,
    vec: &mut Vec<f64>, k1: usize, k2: usize, k3: usize,
) -> Vec<f64> {
    use rayon::prelude::*;
    let mut curve = Vec::with_capacity(plan_batch.len());
    for (step, bidx) in plan_batch.iter().enumerate() {
        let d = joint_loss3(lat_all, bidx, lat_all, r, c, obj_idx, shape_idx,
                            vec, k1, k2, k3);
        curve.push(d);
        let v = vec.clone();
        let sample = &plan_sample[step];
        let updates: Vec<(usize, bool, f64)> = sample
            .par_iter()
            .map(|&pi| {
                let old = v[pi];
                let mut vp = v.clone(); vp[pi] = old + eps;
                let dp = joint_loss3(lat_all, bidx, lat_all, r, c, obj_idx,
                                     shape_idx, &vp, k1, k2, k3);
                let mut vm = v.clone(); vm[pi] = old - eps;
                let dm = joint_loss3(lat_all, bidx, lat_all, r, c, obj_idx,
                                     shape_idx, &vm, k1, k2, k3);
                let g = (dp - dm) / (2.0 * eps);
                (pi, g.abs() >= deadzone, -lr * g.signum())
            })
            .collect();
        for (pi, ok, delta) in updates {
            if ok { vec[pi] += delta; }
        }
    }
    curve
}
