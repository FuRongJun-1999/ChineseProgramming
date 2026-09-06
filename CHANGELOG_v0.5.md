# Protocol Compiler v0.5 · 更新日志

**日期**：2026-09-06
**版本**：v0.5.0（多进程蜂群 · Rust 多线程/多实例扩展）

---

## 荣裁定（2026-09-06 访谈四条）

1. **并发层次**：多实例并行——实例间隔离（ip/栈/符号表/信任/条件空间各自独立），不改指令集。
2. **通信模型**：消息传递——实例间只靠消息（WAL/ACK/HMAC 签名照搬蜂群事件总线语义），无共享可变状态。
3. **信任语义**：实例私有 + 聚合层（对齐 trust_aggregator：T_avg/T_min/T_variance/T_alignment）。
4. **交付形态**：多进程蜂群——独立协调器 + 多个 protocol_vm 子进程（进程隔离，对齐 start_cluster）。

## 新增

### Rust 侧（rust_runtime 模板，仍纯 std 零 crate）✅

- `src/hmac.rs`：**手写 SHA-256 + HMAC-SHA256**（FIPS 180-4 / RFC 2104，FIPS 与 RFC 4231
  测试向量内嵌单测）——零依赖哲学下的密码学原语，用途限蜂群消息签名（对齐 instance_registry B2）。
- `src/serve.rs`：`protocol_vm --serve` **VM 实例化模式**——stdin 逐行 JSON 请求
  `{"symbols","trust","condition_space","round_no"}` → stdout 逐行终态 JSON；进程存活=实例。
  「初始符号」包裹键**展平注入**（协调器包裹的初始环境）；符号表不跨轮持久——每轮完整环境，
  跨轮数据只能走消息（消息传递模型的语义落点）。
- `src/swarm.rs`：**蜂群协调器**——spawn N 实例子进程（stdio 管道）、事件路由
  （收件箱注入：消息=目标实例下一轮「收件箱」符号 + 「已收消息数」）、WAL 落盘
  （events.jsonl append-only）、ACK 回执追踪、HMAC 签名、信任聚合（B6 防操纵：
  0-1 夹取；error 终态沿用上一轮 trust 不推平曲线）。
- CLI：`protocol_vm swarm --config swarm.json --wal events.jsonl`。

### Python 侧 ✅

- `core/rust_swarm.py`：`make_swarm_config`（配置生成）/ `run_swarm`（运行+报告解析）/
  `verify_wal_signatures`（**Python hashlib/hmac 独立复核——交叉验证 Rust 手写 SHA256**）/
  `aggregate_trust_python`（聚合参照实现，对齐 trust_aggregator 操作化定义）。
- `core/rust_codegen.py`：模板拷贝扩至 6 文件；`build_rust_exe` 辅助。

## 验收记录（tests/test_rust_swarm.py 16/16）

| 用例 | 结果 |
|------|------|
| 双实例 3 轮并行执行（同 .pbc 不同初始环境） | 甲 trust=0.9 / 乙 trust=1.0，终态合法 ✓ |
| 消息路由（甲→乙 @trust 占位符→终态信任值） | 乙「已收消息数」=1/轮，收件箱注入 ✓ |
| 信任聚合双端一致 | T_avg=0.95/T_min=0.9/T_var=0.0025/T_align=0.997368，Python 参照逐项吻合 ✓ |
| HMAC 交叉验证 | WAL 5 条全部经 Python hashlib 验签通过（Rust 手写 SHA256 交叉验证）✓ |
| 篡改检测 | payload 改动 → 签名不匹配 ✓ |
| 轮间状态语义 | 符号表不跨轮泄漏（每轮重算）；跨轮数据只经消息 ✓ |
| clippy 零警告 / 既有套件回归 | 0 警告；八套件+v0.4 后端 13/13 全通过，零破坏 ✓ |

## 已声明局限（V0 诚实边界）

- 延迟分级（500ms/5s/30s）仅作 WAL 元数据标记，投递间隔调度为后续版本（V0 同步路由）。
- 事件类型为协调器级路由（信任同步/ACK）；VM 源语言无并发助记符（语言级并发是后续里程碑）。
- 路由 payload 占位符仅 `@trust`；条件空间帧的跨实例聚合未做（实例私有，聚合层只聚合信任）。
- serve 实例标识经环境变量 `PROTOCOL_VM_INSTANCE`（缺省「无名实例」——收件箱语义不受影响，报告回显待接）。
