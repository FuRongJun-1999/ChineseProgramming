//! hex_nn CLI · 确定性训练执行器
//! 用法: hex_nn train <data.bin> <plan.bin> <vec.bin> <out.bin>
//! data.bin:  magic u64=0x4845584441544131("HEXDATA1"), n u64, r u64, c u64,
///           n_obj_labels u32×n, n_shape_labels u32×n, lat f64×(n·r·c·3)
/// vec.bin:   f64×P(初始参数:conv1(K1·7) ++ conv2(K2·K1·7) ++ head(9·(K2+3)))
///            头部: K1 u64, K2 u64
/// out.bin:   magic u64=0x4845584E4E4F5554("HEXNNOUT"), steps u64,
///            D f64×steps, vec f64×P, seconds f64
use std::time::Instant;

fn rd_u64(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    // train_par 模式:线程数通过 RAYON_NUM_THREADS 环境变量控制(rayon 惯例)
    if args.len() != 6 || !(args[1] == "train" || args[1] == "train_par" || args[1] == "train3_par") {
        eprintln!("usage: hex_nn train|train_par <data.bin> <plan.bin> <vec.bin> <out.bin>");
        std::process::exit(2);
    }
    let par3 = args[1] == "train3_par";
    let par = args[1] == "train_par" || par3;
    let data = std::fs::read(&args[2]).unwrap();
    let plan = std::fs::read(&args[3]).unwrap();
    let vecf = std::fs::read(&args[4]).unwrap();

    // ---- data ----
    assert_eq!(rd_u64(&data, 0), 0x4845584441544131, "bad data magic");
    let n = rd_u64(&data, 8) as usize;
    let r = rd_u64(&data, 16) as usize;
    let c = rd_u64(&data, 24) as usize;
    let mut o = 32usize;
    let mut obj_idx = Vec::with_capacity(n);
    for _ in 0..n {
        obj_idx.push(u32::from_le_bytes(data[o..o + 4].try_into().unwrap()) as usize);
        o += 4;
    }
    let mut shape_idx = Vec::with_capacity(n);
    for _ in 0..n {
        shape_idx.push(u32::from_le_bytes(data[o..o + 4].try_into().unwrap()) as usize);
        o += 4;
    }
    let need = n * r * c * 3 * 8;
    assert_eq!(data.len(), o + need, "lat size mismatch");
    let lat: Vec<f64> = data[o..]
        .chunks_exact(8)
        .map(|ch| f64::from_le_bytes(ch.try_into().unwrap()))
        .collect();

    // ---- plan ----
    let (pb, ps) = hex_nn::parse_plan(&plan).unwrap();

    // ---- vec(参数;train3 头部含 K3)----
    let k1 = rd_u64(&vecf, 0) as usize;
    let k2 = rd_u64(&vecf, 8) as usize;
    let k3 = if par3 { rd_u64(&vecf, 16) as usize } else { 0usize };
    let voff = if par3 { 24 } else { 16 };
    let mut vec: Vec<f64> = vecf[voff..]
        .chunks_exact(8)
        .map(|ch| f64::from_le_bytes(ch.try_into().unwrap()))
        .collect();

    // ---- 训练(lr 经 HEX_LR 环境变量,默认 0.1)----
    let lr: f64 = std::env::var("HEX_LR").ok()
        .and_then(|v| v.parse().ok()).unwrap_or(0.1);
    let t0 = Instant::now();
    let curve = if par3 {
        hex_nn::train3_steps_par(&lat, r, c, &obj_idx, &shape_idx,
                                 &pb, &ps, lr, 1e-3, 1e-6,
                                 &mut vec, k1, k2, k3)
    } else if par {
        hex_nn::train_steps_par(&lat, r, c, &obj_idx, &shape_idx,
                                &pb, &ps, lr, 1e-3, 1e-6,
                                &mut vec, k1, k2)
    } else {
        hex_nn::train_steps(&lat, n, r, c, &obj_idx, &shape_idx,
                            &pb, &ps, lr, 1e-3, 1e-6,
                            &mut vec, k1, k2)
    };
    let secs = t0.elapsed().as_secs_f64();

    // ---- out ----
    let mut out = Vec::new();
    out.extend_from_slice(&0x4845584E4E4F5554u64.to_le_bytes());
    out.extend_from_slice(&(curve.len() as u64).to_le_bytes());
    for d in &curve {
        out.extend_from_slice(&d.to_le_bytes());
    }
    for v in &vec {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out.extend_from_slice(&secs.to_le_bytes());
    std::fs::write(&args[5], out).unwrap();
    eprintln!(
        "hex_nn: steps={} D {:?} -> {:?} params={} {:.2}s",
        curve.len(),
        curve.first().map(|d| (d * 1e4).round() / 1e4),
        curve.last().map(|d| (d * 1e4).round() / 1e4),
        vec.len(),
        secs
    );
}
