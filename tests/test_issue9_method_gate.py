# -*- coding: utf-8 -*-
"""test_issue9_method_gate.py · #9 守卫：_should_proceed 的 method 必须参与判定
验证：①P1 白名单生效（登记名过/未登记名拒）②P3 原有两道闸不误杀 ③P4 白名单恰为三入口
本件不依赖 requests / cargo，可独立直跑（python tests/test_issue9_method_gate.py）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.llm_bridge import LLMBridge

pass_n = fail_n = 0
def check(name, ok, detail=''):
    global pass_n, fail_n
    if ok: pass_n += 1
    else: fail_n += 1
    print(f'[{"✓" if ok else "✘"}] {name}{" — " + detail if detail else ""}')

def make_bridge(*, allow=True, connected=True):
    b = LLMBridge.__new__(LLMBridge)          # 跳过 __init__（不建网络/供应商）
    b._connected = connected
    b.spirit = type("S", (), {"should_use_llm": lambda self: allow})()
    return b

# ---- P1 白名单生效 ----
b = make_bridge()
for name in ("understand", "suggest_verification", "explain_term"):
    check(f"P1 登记方法放行：{name}", b._should_proceed(name) is True)
for name in ("任意方法名", "", "Understand", "understand "):
    check(f"P1 未登记方法拒绝：{name!r}", b._should_proceed(name) is False)

# ---- P3 原有两道闸不误杀（登记方法也必须被它们拦住） ----
check("P3a 灵魂层拒绝 ⇒ False", make_bridge(allow=False)._should_proceed("understand") is False)
check("P3b 未连接 ⇒ False", make_bridge(connected=False)._should_proceed("understand") is False)

# ---- P4 白名单恰为文档三入口（防登记名笔误） ----
check("P4 白名单恰为三入口",
      LLMBridge.LLM_ENABLED_METHODS == frozenset(
          {"understand", "suggest_verification", "explain_term"}),
      str(sorted(LLMBridge.LLM_ENABLED_METHODS)))

print(f"\n通过 {pass_n} / 失败 {fail_n}")
if __name__ == "__main__":
    sys.exit(0 if fail_n == 0 else 1)
