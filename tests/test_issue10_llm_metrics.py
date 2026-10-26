# -*- coding: utf-8 -*-
"""test_issue10_llm_metrics.py · #10 守卫：update_failure 的失败原因必须留痕
验证：①Q1 原因留痕 ②Q2 原因聚合 ③Q3 缺省参数 ④Q4 既有行为不误杀 ⑤Q5 实例隔离
本件不依赖 requests / cargo，可独立直跑（python tests/test_issue10_llm_metrics.py）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.llm_bridge import LLMTrustMetrics

pass_n = fail_n = 0
def check(name, ok, detail=''):
    global pass_n, fail_n
    if ok: pass_n += 1
    else: fail_n += 1
    print(f'[{"✓" if ok else "✘"}] {name}{" — " + detail if detail else ""}')

# ---- Q1 原因留痕：update_failure("X") 后 last_error == "X" ----
m = LLMTrustMetrics()
m.update_failure("ConnectionError: timed out")
check("Q1 last_error 留痕", m.last_error == "ConnectionError: timed out",
      repr(getattr(m, "last_error", None)))

# ---- Q2 原因聚合：error_counts 按原因计数 ----
m2 = LLMTrustMetrics()
m2.update_failure("empty_result")
m2.update_failure("empty_result")
m2.update_failure("timeout")
check("Q2 同原因计数为 2、异原因各 1",
      m2.error_counts == {"empty_result": 2, "timeout": 1},
      str(m2.error_counts))

# ---- Q3 缺省参数：update_failure() 落空串键 ----
m3 = LLMTrustMetrics()
m3.update_failure()
check("Q3 缺省 error 落空串键", m3.last_error == "" and m3.error_counts.get("") == 1,
      f"{m3.last_error!r} {m3.error_counts}")

# ---- Q4 不误杀：既有计数/信任值行为逐位不变 ----
m4 = LLMTrustMetrics()
t0 = m4.trust_value
m4.update_failure("a")          # recent=1, penalty=0.03*1.5
t1 = m4.trust_value
m4.update_failure("b")          # recent=2, penalty=0.03*2
t2 = m4.trust_value
check("Q4a 信任值递减序列不变",
      abs((t0 - t1) - 0.045) < 1e-12 and abs((t1 - t2) - 0.06) < 1e-12,
      f"{t0} -> {t1} -> {t2}")
check("Q4b 计数器行为不变",
      m4.total_calls == 2 and m4.recent_failures == 2 and m4.consecutive_successes == 0,
      f"total={m4.total_calls} recent={m4.recent_failures} consec={m4.consecutive_successes}")
m4.update_success(0.5)
check("Q4c 成功路径不受新字段影响",
      m4.successful_calls == 1 and m4.recent_failures == 0
      and m4.last_error == "b",  # 语义：last_error 是「最近一次失败」，成功不清除
      f"last_error={m4.last_error!r}")

# ---- Q5 实例隔离：error_counts 不得跨实例共享（default_factory） ----
a, b = LLMTrustMetrics(), LLMTrustMetrics()
a.update_failure("only_a")
check("Q5 两实例 error_counts 互不共享", b.error_counts == {} and a.error_counts == {"only_a": 1},
      f"a={a.error_counts} b={b.error_counts}")

print(f"\n通过 {pass_n} / 失败 {fail_n}")
if __name__ == "__main__":
    sys.exit(0 if fail_n == 0 else 1)
