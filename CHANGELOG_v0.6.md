# Protocol Compiler v0.6 · 更新日志（草稿——随提交定稿）

**日期**：2026-09-13
**版本**：v0.6.0（蜂群高并发 · RUST-SWARM-REV2）
**驱动**：荣 2026-09-12 指令启动「多智能体高并发」长期任务（心跳持续推进）；B3 裁定 **甲案**（2026-09-13）——自研传输层 Gossip + 四因子评分自算（可复算路线）。

---

## 荣裁定

1. **B3 共识路线：甲案**（2026-09-13）——对照 ruflo 实证其"共识"为 LLM 角色卡（不可复算），甲案 = swarm.rs 自研传输层 Gossip + 健康评分从事件流统计自算，与验证纪律一致。
2. **底座不换**：langgraph/ruflo 仅对照研读（六份研读笔记见 `agi-architectures/研读笔记/`），全部实现落点 `rust_runtime/src/swarm.rs`，纯 std 零新依赖。

## 新增

### B1 断点恢复 ✅

- WAL 轮末快照行（复用事件行格式与 HMAC 签名约定，`type=__snapshot__`，payload 记 trust 水位与终态）
- 启动重放：重建事件史/ACK/收件箱/信任水位；**回滚规则**——快照即提交点，快照后未提交轮次整体回滚（防 kill 落在「事件已写、快照未写」之间时的重放+重跑重复）
- 坏尾截断：半行/篡改（HMAC 守卫）→ 截断续跑；已完成轮数 ≥ 目标 → 幂等聚合
- 落盘顺序纪律：事件行 flush 后快照行 sync_all——快照永不先于产生它的写入落盘
- Python `verify_wal_signatures` 对快照行验签但不计入事件数（旧断言零改动）

### B2 轮内并行超步 ✅

- `std::thread::scope` 轮内并行（一实例一线程一管道，`&mut` 独占借用），join 收齐即屏障
- 屏障后按实例声明序处理——事件序/WAL 行序与串行版完全一致
- 基准：加速比 2.38×@8 实例（VM 计算轻时屏障开销主导，计算越重越趋近 N×）

### G3 健康评分 + Gossip + 对账闭环（甲案主体）✅

- **`health.rs`（新模块）**：四因子评分 `score = 0.4×success + 0.2×uptime + 0.2×(1−threat) + 0.2×integrity`，全部从轮次终态序列统计（对照 ruflo 同公式，但可复算）；报告新增 `health` 字段
- **Gossip 广播**：`Route.to_id = "*"` fan-out 至除源外全部实例，每目标独立 HMAC 事件
- **水位对账**：`gossip_sent` 记账 + `gossip_consistent`（全部目标实收相等）；**coverage 接入 integrity 因子**（实收/对账基准）
- Python `aggregate_health_python` 参照实现（双端公式一致）

### G4 拓扑 + 版本化信箱 ✅

- **拓扑三型**：`hierarchical`（首实例 queen）/ `centralized`（coordinator）/ `mesh`（全 peer）；缺省保持用户声明 role（向后兼容）；未知拓扑报错；报告透出 `topology`/`roles`
- **版本化信箱**：投递消息带全局单调 `seq`；ACK payload 携带消费水位（payload 在 HMAC 签名串内，自动受保护）；报告 `watermarks`/`global_seq`；恢复场景重放计数保持 seq 不断档

### G5 实例级容错 ✅

- 管道断裂 → 同线程重建实例进程重跑该轮（幂等：每轮从完整环境起算）
- 重试仍失败 → dead 退场（outcomes 记 None、uptime 降、蜂群继续）
- 端到端验收：运行中强杀 2 个 `--serve` 实例 → 蜂群 rc=0 无感完成，终态与基线逐项一致（透明容错）

## 修复

- **integrity 通路接通**（v0.6.1 · 2026-09-13 蜂群实测审计发现）：`aggregate_report` 此前调用 `score_instance` 时硬编码 `verify_fail=0, total_events=1`，integrity 因子退化为纯 gossip 覆盖率。修正为事件流逐条重验签名（归属 = `from_id`，快照行不计事件口径，与 Python `verify_wal_signatures` 一致）。单机在线自签自验恒过 + 重放事件已过坏尾守卫 → **数值与 v0.6 完全等价（零回归）**；跨机/直接注入事件流场景验签失败真实降级——数据通路自此不再硬编码。附 `health.rs` Rust 单测 2 项（verify_fail 降级公式 / 零事件回退 coverage，补测试盲区）
- **功能说明 §五上手缺陷**（实测 A4 评审发现）：示例缺 `generate_rust_project` 前置步骤（`project_dir` 来源未讲，照抄必失败）；`run_swarm` 展示签名与真实签名不一致。重写为五步照抄可跑示例（与 `test_swarm_health.py` 同构）+ 完整签名说明
- **coverage 边界**（G5 调试暴露）：纯源实例（`gossip_sent` 无键）被误判 coverage=0 → integrity 归零、score 恒 0.8；修正为无键 = 非 gossip 目标 → 1.0
- **B1 回滚缺口**（kill 演练推演暴露）：重放会把「快照后未提交轮次」的部分事件重建进收件箱且该轮又被重跑 → 事件重复；修正为提交点回滚
- `rust_codegen.py`：模板复制名单补 `health.rs`（新 .rs 必须同步复制名单，否则生成项目编译失败）

## 验收记录（2026-09-13，v0.6.1 复跑八套全绿）

总账：八套回归 107 项全绿 + Rust lib 单测 4 项 + clippy 零警告。

| 套件 | 覆盖 | 结果 |
|------|------|------|
| `test_rust_swarm.py` | 既有基线（路由/ACK/验签/聚合/独立形态） | 20/20 |
| `test_rust_swarm_resume.py` | B1 分段恢复/幂等/坏尾截断 | 15/15 |
| `test_rust_swarm_kill.py` | C1 强杀协调器 + 真实中途点续跑 | 11/11 |
| `test_swarm_health.py` | G3a 公式场景 + 双端一致 + ③integrity 通路 WAL 独立复算对照（v0.6.1 新增 3 项） | 13/13 |
| `test_swarm_gossip.py` | G3b/G3c 广播/对账/共存/纯源回归 | 17/17 |
| `test_swarm_topology.py` | G4a 三型推导/兼容/校验 | 11/11 |
| `test_swarm_watermark.py` | G4b seq 单调/水位/恢复不断档 | 11/11 |
| `test_swarm_fault.py` | G5 真杀双实例透明容错 | 9/9 |
| `health.rs` lib 单测 | v0.6.1 verify_fail 公式/零事件回退 | 4/4 |
| clippy | `--no-default-features -D warnings` | 零警告 |

性能基准（可复跑）：`bench_swarm_parallel.py`（加速比）、`bench_swarm_scale.py`（规模扫描 N=1→64 摊薄不升、吞吐 12218 events/s@16 实例）。

## 已声明局限

- gossip 对账口径为单机投递覆盖断言（跨机网络故障域留跨机版）
- health/watermark 的恢复场景为在线窗口口径（重放前轮次不重计）
- dead 分支（重试仍败退场）已实现，确定性触发留长稳/跨机验证
- 邻接表连接约束/分区复制未实现（单机全连语义下无路由意义）
- md_cg 向量第 5 路：评估后暂不做（A4 取证，升级条件 >5 万节点且语义需求明确）
