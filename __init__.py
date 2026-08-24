"""
protocol-compiler · 协议编译器
将协议源代码（中文 + 道德经助记符 + 九章算术结构）编译为兼容的 Python 代码

架构：
- core/        编译器核心（词法/语法/名实/生成/LLM桥接）
- cli/         人类开发者接口
- mcp/         AI Agent 接口（后续实现）
- runtime/      protocol_runtime（独立维护模块）

v0.2.0 新增：
- LLM 桥接层（Kimi 首选 / DeepSeek 备选 / 自定义兼容）
- 自我诊断能力（供自维持系统调用）
- 灵魂层代理接口（预留 spacetime-memory-engine 接入）
- 多词短语自动声明
- 赋值语句支持（= 和 ＝）
- 宽松标识符模式（指令操作数不再硬报错）
"""
__version__ = "0.2.0"
