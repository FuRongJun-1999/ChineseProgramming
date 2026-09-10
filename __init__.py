"""
protocol-compiler · 协议编译器
将协议源代码（中文 + 道德经助记符 + 九章算术结构）编译为可执行的字节码 / 代码

架构：
- core/          编译器核心（词法/语法/名实/生成/字节码 VM/Rust codegen/蜂群）
- cli/           人类开发者接口
- rust_runtime/  Rust VM 模板（纯 std 零外部 crate）
- hex_nn/        白箱原生神经网络 Rust 性能后端
- mcp/           AI Agent 接口（后续实现）

版本路线：
- v0.2.0  LLM 桥接层（Kimi/DeepSeek）· 自我诊断 · 灵魂层代理接口
- v0.3.0  智能论字节码 VM（condition_vm）——条件空间/信任成为 VM 内建状态
- v0.4.0  Rust 原生后端——AST → .pbc 字节码 → Rust 独立解释器（纯 std 零 crate）
- v0.5.0  多进程蜂群（--serve 实例化 + 协调器 + WAL/ACK/HMAC + 信任聚合）
          · hex_nn 白箱原生神经网络 Rust 后端（R1 串行 / R2 rayon 并行）
"""
__version__ = "0.5.0"
