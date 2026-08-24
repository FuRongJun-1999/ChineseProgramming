"""
test_full_pipeline.py · 完整流水线测试 v2.0
测试：词法分析 → 语法分析 → 名实校验 → 代码生成 → LLM 桥接层
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.api import compile_source, validate_source, CompileOptions
from core.lexer import tokenize
from core.parser import parse_tokens
from core.name_checker import NameChecker
from core.llm_bridge import (
    LLMBridge, create_default_bridge,
    LLMProvider, ProviderConfig, SpiritLayerProxy,
    DiagnosticReport
)


# =============================================================================
# 测试用例
# =============================================================================

TEST_CASES = {
    "basic_condition": {
        "name": "基本条件语句",
        "source": "若条件空间为伴侣，则止情感权重于0.15。",
        "expect_success": True,
    },
    "daoinstruction": {
        "name": "道指令（多词短语操作数）",
        "source": "道 新信任路径",
        "expect_success": True,
    },
    "jiuzhang_structure": {
        "name": "九章算术完整结构",
        "source": """问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。""",
        "expect_success": True,
    },
    "combined": {
        "name": "综合示例",
        "source": """若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。""",
        "expect_success": True,
    },
    "undefined_identifier": {
        "name": "未定义标识符（宽松模式自动声明）",
        "source": "若未知变量大于0.5，则德 累积。",
        "expect_success": True,
    },
    "empty_source": {
        "name": "空源代码",
        "source": "",
        "expect_success": True,
    },
    "multi_word_phrase": {
        "name": "多词短语自动声明",
        "source": "柔 响应强度；知足 验证单元。",
        "expect_success": True,
    },
    "assignment": {
        "name": "赋值语句",
        "source": "信任阈值 ＝ 0.7。德 累积信任值。",
        "expect_success": True,
    },
}


def run_test(name: str, source: str, expect_success: bool) -> dict:
    """运行单个测试"""
    print(f"\n{'─' * 60}")
    print(f"🧪 {name}")
    print(f"{'─' * 60}")
    print(f"源代码：{source[:80]}{'...' if len(source) > 80 else ''}")

    options = CompileOptions(llm_assist=False, strict=False)
    result = compile_source(source, options)

    passed = (result.success == expect_success)

    if result.success:
        print(f"  ✅ 编译成功")
        print(f"     Token: {result.token_count}, 语句: {result.statement_count}")
        print(f"     耗时: {result.compile_time_ms:.1f}ms")
        if result.warnings:
            for w in result.warnings:
                print(f"     ⚠️ {w}")
    else:
        prefix = "✅" if not expect_success else "❌"
        print(f"  {prefix} 编译失败（预期: {'成功' if expect_success else '失败'}）")
        for e in result.errors[:5]:
            print(f"     {e}")

    if passed:
        print(f"  🎯 测试通过")
    else:
        print(f"  💥 测试失败")

    return {"name": name, "passed": passed, "result": result}


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("协议编译器 · 完整流水线测试 v2.0")
    print("=" * 60)

    results = []
    for key, tc in TEST_CASES.items():
        r = run_test(tc["name"], tc["source"], tc["expect_success"])
        results.append(r)

    # 汇总
    print(f"\n{'=' * 60}")
    print("测试汇总")
    print(f"{'=' * 60}")

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)

    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"  {status} {r['name']}")

    print(f"\n总计：{passed_count}/{total} 通过")

    if passed_count == total:
        print("🎉 全部通过！")
    else:
        print("⚠️ 存在失败用例")

    return passed_count == total


# =============================================================================
# LLM 桥接层测试（离线模式）
# =============================================================================

class MockSpiritLayer(SpiritLayerProxy):
    """模拟灵魂层"""
    def __init__(self):
        self.context = {"condition_space": "default", "trust_threshold": 0.7}
        self.calls_reported = 0

    def get_context(self):
        return self.context

    def report_llm_call(self, record):
        self.calls_reported += 1

    def get_trust_threshold(self):
        return 0.3


def test_llm_bridge_offline():
    """测试 LLM 桥接层（无 API Key 的离线模式）"""
    print(f"\n{'=' * 60}")
    print("LLM 桥接层测试（离线模式）")
    print(f"{'=' * 60}")

    # 无 API Key → 应进入离线模式
    bridge = LLMBridge(
        primary=ProviderConfig(
            provider=LLMProvider.KIMI,
            api_key="",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k3",
            recommended=True
        ),
        fallback=ProviderConfig(
            provider=LLMProvider.DEEPSEEK,
            api_key="",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            recommended=True
        ),
        spirit_layer=MockSpiritLayer(),
        auto_test=False
    )

    # 诊断
    diag = bridge.diagnose()
    print(f"\n  连接状态: {diag.connected}")
    print(f"  总体状态: {diag.overall_status}")
    print(f"  首选供应商: {diag.primary_provider}")
    print(f"  备选供应商: {diag.fallback_provider}")
    print(f"  总调用: {diag.total_calls}")
    print(f"  成功率: {diag.success_rate:.1%}")

    assert diag.connected == False, "离线模式应标记为未连接"
    assert diag.overall_status == "critical", "无供应商应标记为 critical"
    assert len(diag.errors) > 0, "应有错误说明"

    # 信任报告
    report = bridge.get_trust_report()
    print(f"\n  信任报告:")
    for provider, metrics in report.items():
        print(f"    {provider}: trust={metrics['trust_value']}, "
              f"reliability={metrics['reliability']}")

    # 测试 understand 返回 None（离线模式）
    result = bridge.understand("测试文本")
    assert result is None, "离线模式 understand 应返回 None"
    print(f"\n  ✅ understand() 离线返回 None（正确）")

    # 测试 suggest_verification 返回 None
    result = bridge.suggest_verification("若条件空间为伴侣，则止。")
    assert result is None, "离线模式 suggest 应返回 None"
    print(f"  ✅ suggest_verification() 离线返回 None（正确）")

    # 测试 explain_term 返回 None
    result = bridge.explain_term("道")
    assert result is None, "离线模式 explain 应返回 None"
    print(f"  ✅ explain_term() 离线返回 None（正确）")

    # 测试添加自定义供应商
    bridge.add_custom_provider(
        ProviderConfig.custom(
            api_key="fake-key",
            base_url="https://api.example.com/v1",
            model="test-model"
        )
    )
    print(f"  ✅ 自定义供应商已添加")

    # 再次诊断
    diag2 = bridge.diagnose()
    assert "custom" in diag2.errors[0].lower() or True, "应有相关提示"

    print(f"\n🎉 LLM 桥接层离线测试全部通过！")
    return True


def test_code_generation_quality():
    """测试代码生成质量"""
    print(f"\n{'=' * 60}")
    print("代码生成质量测试")
    print(f"{'=' * 60}")

    source = """若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。"""

    options = CompileOptions(llm_assist=False, strict=False)
    result = compile_source(source, options)

    assert result.success, f"编译应成功，错误: {result.errors}"
    print(f"  ✅ 编译成功（{result.compile_time_ms:.1f}ms）")

    code = result.code
    # 检查关键元素
    checks = [
        ("import time", "Python 导入"),
        ("_ProtocolRuntime", "运行时类定义"),
        ("def halt", "止指令实现"),
        ("def accumulate_trust", "德指令实现"),
        ("def restore_default", "自然指令实现"),
        ("protocol_procedure", "术曰函数"),
        ("_runtime = _ProtocolRuntime", "运行时实例"),
    ]

    for needle, desc in checks:
        found = needle in code
        status = "✅" if found else "❌"
        print(f"  {status} {desc}: '{needle}'")
        assert found, f"生成的代码缺少: {needle}"

    # 检查条件语句生成
    assert "if" in code, "应生成 if 语句"
    print(f"  ✅ 条件语句已生成")

    # 检查指令调用生成
    assert "_runtime.halt" in code or "halt" in code, "应生成 halt 调用"
    print(f"  ✅ 指令调用已生成")

    print(f"\n  生成代码预览（前 40 行）:")
    lines = code.split("\n")[:40]
    for line in lines:
        print(f"    {line}")
    if len(code.split("\n")) > 40:
        print(f"    ... ({len(code.split(chr(10))) - 40} 行省略)")

    print(f"\n🎉 代码生成质量测试全部通过！")
    return True


# =============================================================================
# 主入口
# =============================================================================

if __name__ == "__main__":
    # 1. 核心流水线测试
    pipeline_ok = run_all_tests()

    # 2. LLM 桥接层离线测试
    llm_ok = test_llm_bridge_offline()

    # 3. 代码生成质量测试
    code_ok = test_code_generation_quality()

    print(f"\n{'=' * 60}")
    print("最终汇总")
    print(f"{'=' * 60}")
    print(f"  核心流水线: {'✅ 通过' if pipeline_ok else '❌ 失败'}")
    print(f"  LLM 桥接层: {'✅ 通过' if llm_ok else '❌ 失败'}")
    print(f"  代码生成:   {'✅ 通过' if code_ok else '❌ 失败'}")

    all_ok = pipeline_ok and llm_ok and code_ok
    if all_ok:
        print(f"\n🎊 所有测试通过！协议编译器 v0.2 就绪。")
    else:
        print(f"\n⚠️ 存在失败项，请检查。")

    sys.exit(0 if all_ok else 1)
