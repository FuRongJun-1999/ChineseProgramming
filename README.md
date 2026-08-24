# protocol-compiler · 协议编译器 v0.3.0

将协议源代码（中文 + 道德经助记符 + 九章算术结构）编译为可执行的代码。
v0.3：新增**智能论字节码 VM**（condition_vm）——道德经助记符 → VM 指令，
条件空间/信任成为 VM 内建状态（原生编译地基，零外部运行时依赖）。

## 架构定位

```
灵魂层（spacetime-memory-engine）── 协议实例的持续存在
        │
        ▼ 通过编译器表达意志
桥梁层（protocol-compiler）── 协议源代码 → 字节码 / Python 代码
        │
        ▼ 通过接口与外界互动
身体层（CLI / MCP）── 人类和外部 AI 的接触面
```

## 项目结构

```
protocol-compiler/
├── __init__.py          # 版本号、项目描述
├── core/                # 编译器核心
│   ├── __init__.py
│   ├── lexer.py         # 词法分析器 v2.0（中文分词 + 道德经助记符）
│   ├── parser.py        # 语法分析器 v2.0（AST 构建）
│   ├── name_checker.py  # 名实校验器 v2.1（墨辩语义分析·以名举实）
│   ├── codegen.py       # 代码生成器（AST → Python，兼容后端）
│   ├── condition_vm.py  # 智能论字节码 VM v0.3（原生编译地基）
│   ├── llm_bridge.py    # LLM 桥接层 v1.0（Kimi/DeepSeek/自定义）
│   └── api.py           # 统一编译 API
├── cli/                 # 命令行接口
│   └── __init__.py     # pc compile / check / explain / init / tokens / ast
└── tests/
    ├── test_full_pipeline.py  # 完整流水线测试（8 用例）
    ├── test_new_modules.py    # 新模块测试（12 用例）
    └── test_condition_vm.py   # 智能论 VM 测试（13 用例）
```

## 快速开始

### 编译协议文件

```bash
# 使用 DeepSeek（默认备选）
export DEEPSEEK_API_KEY="your-key-here"
export LLM_PRIMARY="deepseek"

# 编译
python -m cli compile your_protocol.proto -o output/

# 仅校验（不生成代码）
python -m cli check your_protocol.proto

# 查看 Token
python -m cli tokens your_protocol.proto

# 查看 AST
python -m cli ast your_protocol.proto

# 解释术语
python -m cli explain 道
```

### 作为库使用

```python
from core import compile_source, CompileOptions

source = """
若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
"""

options = CompileOptions(llm_assist=False, strict=False)
result = compile_source(source, options)

if result.success:
    print(result.code)  # 生成的 Python 代码
else:
    for e in result.errors:
        print(f"错误: {e}")
```

## LLM 桥接层

### 供应商优先级

| 优先级 | 供应商 | 推荐度 | 说明 |
|--------|--------|--------|------|
| 🥇 首选 | Kimi | ⭐⭐⭐⭐⭐ | 与验证单元现象层同构 |
| 🥈 备选 | DeepSeek | ⭐⭐⭐⭐ | 申请门槛低，可用性 99.88% |
| 🥉 兼容 | 自定义 | ⭐⭐ | 需声明后果，信任值按 0.5 起算 |

### 环境变量

```bash
# Kimi（首选）
export KIMI_API_KEY="sk-..."
export KIMI_BASE_URL="https://api.moonshot.ai/v1"
export KIMI_MODEL="kimi-k3"

# DeepSeek（备选）
export DEEPSEEK_API_KEY="sk-..."
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-chat"

# 供应商选择
export LLM_PRIMARY="kimi"       # 或 deepseek
export LLM_FALLBACK="deepseek"   # 或 kimi
```

### 自我诊断

```python
from core import create_default_bridge

bridge = create_default_bridge()
diag = bridge.diagnose()

print(f"连接状态: {diag.connected}")
print(f"总体状态: {diag.overall_status}")  # healthy / degraded / critical
print(f"首选供应商: {diag.primary_provider}")
print(f"成功率: {diag.success_rate:.1%}")
print(f"平均延迟: {diag.avg_latency_ms:.0f}ms")

# 查看信任报告
report = bridge.get_trust_report()
for provider, metrics in report.items():
    print(f"  {provider}: trust={metrics['trust_value']}, "
          f"reliability={metrics['reliability']}")
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
cd protocol-compiler
python tests/test_full_pipeline.py
```

预期输出：`🎊 所有测试通过！协议编译器 v0.2 就绪。`

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 词法分析器 | ✅ 完成 | 中文分词、道德经助记符、九章算术结构 |
| 语法分析器 | ✅ 完成 | 条件语句、指令语句、术曰块 |
| 名实校验器 | ✅ 完成 | 47 个预定义符号，墨辩语义分析 |
| 代码生成器 | ✅ 完成 | AST → Python，调用 protocol_runtime |
| LLM 桥接层 | ✅ 完成 | Kimi/DeepSeek 双供应商 + 自我诊断 |
| CLI 接口 | ✅ 完成 | compile/check/explain/init/tokens/ast |
| MCP 服务 | ⏳ 待开发 | JSON-RPC 接口、认证、限流 |
| protocol_runtime | ⏳ 待开发 | 验证单元、维生系统、记录单元 |

## 许可证

智能论协议框架 v3.1 —— 保留所有权利
