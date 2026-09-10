# protocol-compiler · 协议编译器 v0.5.0

将协议源代码（中文 + 道德经助记符 + 九章算术结构）编译为可执行的**字节码 / 代码**，
并提供 **双后端**（Python VM / Rust 原生 VM）与**多进程蜂群**运行时。

| 版本 | 主题 | 状态 |
|------|------|------|
| v0.2 | LLM 桥接层（Kimi/DeepSeek）· 自我诊断 · 灵魂层代理接口 | ✅ |
| v0.3 | 智能论字节码 VM（condition_vm）——条件空间/信任成为 VM 内建状态 | ✅ |
| v0.4 | **Rust 原生后端**——AST → `.pbc` 字节码 → Rust 独立解释器（纯 std 零 crate） | ✅ |
| v0.5 | **多进程蜂群**——`--serve` 实例化 + 协调器 + WAL/ACK/HMAC + 信任聚合；`hex_nn` 原生神经网络 Rust 后端 | ✅ |

## 架构定位

```
灵魂层（spacetime-memory-engine）── 协议实例的持续存在
        │
        ▼ 通过编译器表达意志
桥梁层（protocol-compiler）── 协议源代码 → 字节码 / Python / Rust
        │
        ▼ 通过接口与外界互动
身体层（CLI / MCP）── 人类和外部 AI 的接触面
```

**编译路线（v0.4 裁定）**：AST → 智能论字节码（`.pbc`）→ Rust。
Rust 侧是 `.pbc` 的**独立解释器**（对齐「零 Python 运行时依赖」定位），**非** AST→Rust 源码直译。

## 项目结构

```
protocol-compiler/
├── __init__.py              # 版本号与项目描述
├── core/                    # 编译器核心（17 模块）
│   ├── lexer.py             # 词法分析器 v2.0（中文分词 + 道德经助记符）
│   ├── parser.py            # 语法分析器 v2.0（AST 构建）
│   ├── name_checker.py      # 名实校验器（墨辩语义分析·以名举实）
│   ├── codegen.py           # 代码生成器（AST → Python，兼容后端）
│   ├── compiler.py          # 编译流水线（analyzer/compiler/pbc 主线）
│   ├── analyzer.py          # 分析器 F3-F5（符号表转储/调用图/数据流）
│   ├── condition_vm.py      # 智能论字节码 VM（Python 侧基准实现）
│   ├── pbc.py               # .pbc 序列化/反序列化（tag0-tag6）
│   ├── debugger.py          # 字节码调试器（单步/状态转储）
│   ├── rust_codegen.py      # AST → 字节码 → Rust cargo 项目（include_bytes! 嵌入 .pbc）
│   ├── rust_swarm.py        # 蜂群配置生成 / 运行 / WAL 验签 / 信任聚合参照实现
│   ├── trust_engine.py      # 信任引擎（P_trust / P_gap）
│   ├── info_gap_engine.py   # 信息差引擎（D_norm 四维加权）
│   ├── llm_bridge.py        # LLM 桥接层（Kimi/DeepSeek/自定义 + 自我诊断）
│   ├── protocol_prompt.py   # 协议系统提示词构建
│   └── api.py               # 统一编译 API
├── cli/                     # 命令行接口（python -m cli）
├── rust_runtime/            # Rust VM 模板（纯 std 零外部 crate）
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs          # 执行入口（--trust / --symbols / --serve / swarm）
│       ├── vm.rs            # VM 解释器（ip+值栈+符号表+条件空间栈+信任寄存器+调用栈帧）
│       ├── pbc.rs           # .pbc 反序列化（与 Python 侧逐字节对齐）
│       ├── hmac.rs          # 手写 SHA-256 + HMAC-SHA256（FIPS 180-4 / RFC 2104）
│       ├── serve.rs         # VM 实例化模式（stdin/stdout 逐行 JSON，进程存活=实例）
│       └── swarm.rs         # 蜂群协调器（spawn/路由/WAL/ACK/签名/信任聚合）
├── hex_nn/                  # 白箱原生神经网络 · Rust 性能后端（rayon 并行）
│   ├── Cargo.toml
│   └── src/{lib.rs, main.rs}
├── tests/                   # 10 个测试套件（见「测试」）
├── examples/                # trust.proto / companion.proto
├── docs/                    # 函数命名规范 v1.0 · 调用缺陷四例实测报告
└── requirements.txt
```

## 快速开始

### 编译 / 校验 / 查看

```bash
python -m cli compile  your_protocol.proto -o output/   # 编译为 Python 兼容代码
python -m cli check    your_protocol.proto              # 仅校验（名实 + 语法）
python -m cli tokens   your_protocol.proto              # 查看 Token
python -m cli ast      your_protocol.proto              # 查看 AST
python -m cli explain  道                               # 解释助记符
python -m cli init     my_project                       # 初始化脚手架
python -m cli version                                   # 版本信息
```

### 字节码（第六阶段 C3：零 Python 运行时依赖）

```bash
python -m cli pbc your_protocol.proto -o out.pbc        # 中文源码 → .pbc 字节码
python -m cli run out.pbc --set 名=值 --trust 0.5        # Python VM 加载执行
python -m cli debug out.pbc --set 名=值                  # 字节码单步调试
```

### Rust 后端（v0.4）

```bash
python -m cli rust your_protocol.proto -o out/rust_proj \
    --set 名=值 --trust 0.5 [--no-run]
```

生成一个自包含 cargo 项目：`Cargo.toml + src/{main,vm,pbc,hmac,serve,swarm}.rs + program.pbc`
（`.pbc` 以 `include_bytes!` 编译期嵌入）+ `build_meta.json` 编译元数据（可审计）。

> **前置要求**：仅 Rust 后端需要 [Rust 工具链](https://rustup.rs/)（`cargo`）。
> 不装 Rust 时，纯 Python 路径（compile / pbc / run / debug）**完全可用**——
> Rust 是可选的高性能后端，不是运行前提。

### 作为库使用

```python
from core import compile_source, CompileOptions

source = """
若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
"""

result = compile_source(source, CompileOptions(llm_assist=False, strict=False))
if result["ok"]:
    print(result["code"])
```

```python
from core.rust_codegen import generate_rust_project, build_and_run
gen = generate_rust_project(source, "out/proj")          # → cargo 项目
res = build_and_run("out/proj", symbols={"信任值": 0.8}, trust=0.6)
```

## 双后端语义等价（v0.4 验收标准）

**同一 `.pbc`，Python VM 与 Rust VM 终态一致**——这是双后端可证伪的等价判据。

| 用例 | Python VM | Rust VM | 等价 |
|------|-----------|---------|------|
| trust 样例（道/德/若/止） | trust=0.8, halt | trust=0.8, halt | ✓ |
| 循环（当…执行 计数 0→3） | 计数=3, trust=0.6 | 计数=3, trust=0.6 | ✓ |
| 递归阶乘 4!（CALL tag6 路径） | 结果=24 | 结果=24 | ✓ |
| 多函数互调（双倍/计算） | 结果=11 | 结果=11 | ✓ |

`.pbc` 格式 **tag6** = `(i64 入口 ip + str列表 参数名)`（CALL 签名序列化，v0.4 扩展、向后兼容）。

**已声明局限**：Python 无限精度整数不模拟（i64 溢出降级 Float）· 字符串不参与算术 ·
跨类型比较报错（对齐 Python3 TypeError）· trust 序列化表示差异（`2` vs `2.0`）用数值容差对照。

## 多进程蜂群（v0.5）

**荣裁定（2026-09-06）**：多实例并行（进程隔离）· 消息传递（无共享可变状态）·
实例私有信任 + 聚合层 · 独立协调器 + 多个 `protocol_vm` 子进程。

- `--serve`：**VM 实例化模式**——stdin 逐行 JSON 请求
  `{"symbols","trust","condition_space","round_no"}` → stdout 逐行终态 JSON；**进程存活 = 实例**。
  符号表不跨轮持久（每轮完整环境），**跨轮数据只能走消息**。
- `swarm`：`protocol_vm swarm --config swarm.json --wal events.jsonl`
  —— spawn N 实例（stdio 管道）· 事件路由（收件箱注入）· WAL 落盘（`events.jsonl` append-only）·
  ACK 回执追踪 · HMAC 签名 · 信任聚合（`T_avg / T_min / T_variance / T_alignment`）。
- `hmac.rs`：**手写 SHA-256 + HMAC-SHA256**（FIPS 180-4 / RFC 2104，测试向量内嵌单测）——
  零依赖哲学下的密码学原语，用途限蜂群消息签名。
- Python 侧 `core/rust_swarm.py` 提供 `make_swarm_config` / `run_swarm` /
  **`verify_wal_signatures`（hashlib 独立复核，交叉验证 Rust 手写 SHA256）** / `aggregate_trust_python`。

**已声明局限（V0 诚实边界）**：延迟分级仅作 WAL 元数据标记（V0 同步路由）·
事件类型为协调器级路由（VM 源语言无并发助记符）· payload 占位符仅 `@trust` ·
条件空间帧跨实例聚合未做（聚合层只聚合信任）。

## hex_nn · 白箱原生神经网络 Rust 后端

**零链式法则**：有限差分符号更新（±eps 前向算 g，`|g| < 1e-6` 支路冻结）。

**纪律**：随机决策（plan）由 Python 预生成，**Rust 是确定性执行器**——
同 plan 必须逐位复现 D 曲线。语义源：`aeis/hex_train.py` + `hex_hier.py`（参考实现）。

```bash
hex_nn train     <data.bin> <plan.bin> <vec.bin> <out.bin>   # R1 串行
hex_nn train_par <data.bin> <plan.bin> <vec.bin> <out.bin>   # R2 rayon 并行（RAYON_NUM_THREADS）
hex_nn train3_par <data.bin> <plan.bin> <vec.bin> <out.bin>  # R2 三卷积层并行
```

产物 `out.bin`：`magic("HEXNNOUT") + steps + D[] + vec + seconds`。
**验收**：与 Python 参考实现 D 曲线逐点对照（数值容差）。

## LLM 桥接层

| 优先级 | 供应商 | 说明 |
|--------|--------|------|
| 🥇 首选 | Kimi | 与验证单元现象层同构 |
| 🥈 备选 | DeepSeek | 申请门槛低 |
| 🥉 兼容 | 自定义 | 需声明后果，信任值按 0.5 起算 |

```bash
export KIMI_API_KEY="sk-..."          # 或 DEEPSEEK_API_KEY
export LLM_PRIMARY="kimi"             # 或 deepseek
export LLM_FALLBACK="deepseek"
```

```python
from core import create_default_bridge
diag = create_default_bridge().diagnose()
print(diag.connected, diag.overall_status, diag.primary_provider, diag.success_rate)
```

## 协议源代码示例

```
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：
1。道 新信任路径；
2。若条件空间为伴侣，则止情感权重于0.15；
3。德 累积信任值；
4。自然 恢复默认。
```

## 测试

```bash
python tests/test_full_pipeline.py     # 完整流水线
python tests/test_new_modules.py       # 新模块
python tests/test_condition_vm.py      # 智能论 VM（13）
python tests/test_pbc.py               # .pbc 序列化（5）
python tests/test_compiler_c2.py       # 编译器 C2（12）
python tests/test_c4_tooling.py        # C4 工具链（8）
python tests/test_func_compile.py      # 函数/递归编译（10）
python tests/test_loop_compile.py      # 循环编译（11）
python tests/test_rust_codegen.py      # Rust 双后端等价（13/13）
python tests/test_rust_swarm.py        # 多进程蜂群（16/16）
```

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 词法分析器 | ✅ 完成 | 中文分词、道德经助记符、九章算术结构 |
| 语法分析器 | ✅ 完成 | 条件语句、指令语句、术曰块、函数定义/调用/递归 |
| 名实校验器 | ✅ 完成 | 预定义符号，墨辩语义分析 |
| 代码生成器 | ✅ 完成 | AST → Python 兼容代码 |
| 智能论字节码 VM | ✅ 完成 | Python 侧 `.pbc` 基准解释器（条件空间/信任内建） |
| **Rust 原生后端** | ✅ 完成 | `.pbc` 独立解释器，纯 std 零 crate，双后端等价验收 |
| **多进程蜂群** | ✅ 完成 | `--serve` 实例化 + 协调器 + WAL/ACK/HMAC + 信任聚合 |
| **hex_nn 原生神经网络** | ✅ 完成 | 白箱 Rust 性能后端（R1 串行 / R2 rayon 并行） |
| LLM 桥接层 | ✅ 完成 | Kimi/DeepSeek 双供应商 + 自我诊断 |
| CLI 接口 | ✅ 完成 | compile/check/explain/init/tokens/ast/pbc/run/debug/rust/version |
| 分析器 F3-F5 | ✅ 完成 | 符号表转储 / 调用图 / 数据流 |
| MCP 服务 | ⏳ 待开发 | JSON-RPC 接口、认证、限流 |

## 许可证

智能论协议框架 v3.4 —— 保留所有权利
