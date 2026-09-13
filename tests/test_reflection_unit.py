# -*- coding: utf-8 -*-
"""test_reflection_unit.py · 反思单元验收（智能论 §3.12 二级回溯操作化 · 2026-09-13）
荣给两问句的落地验证：
① 隐藏前提——正常报告全前提成立；注入破坏（gossip_consistent=False / error 终态）
   后对应前提转破；
② 影响推演——前提破坏沿路由表推演波及面（integrity 降级 / 信任沿用受染下游）。
"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\Program Files\2_ai\protocol-compiler")

from core.rust_codegen import generate_rust_project
from core.rust_swarm import make_swarm_config, run_swarm
from core.reflection_unit import reflect

pass_n = fail_n = 0


def check(name, ok, detail=""):
    global pass_n, fail_n
    if ok:
        pass_n += 1
    else:
        fail_n += 1
    print(f'[{"✓" if ok else "✘"}] {name}{" — " + detail if detail else ""}')


SOURCE = """问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：
1。道 新信任路径；
2。德 0.3；
3。若 信任值 大于 0.2，则 德 0.5；
4。止。
"""
SECRET = "验收密钥-反思单元"

tmp = tempfile.mkdtemp(prefix="swarm_reflect_")
proj = os.path.join(tmp, "proj")
generate_rust_project(SOURCE, proj)

ROUTES = [{"from": "实例甲", "event_type": "gossip", "to": "*",
           "payload": "@trust", "level": 0}]


# ============ ① 正常蜂群：反思结论=一致 ============
print("=== ① 正常蜂群反思 ===")
cfg = make_swarm_config(
    instances=[
        {"id": "实例甲", "role": "源", "trust": 0.1, "symbols": {"信任值": 0.5}},
        {"id": "实例乙", "role": "peer", "trust": 0.2, "symbols": {"信任值": 0.5}},
    ],
    routes=ROUTES, rounds=2, shared_secret=SECRET)
rr = run_swarm(proj, cfg, wal_path=os.path.join(tmp, "a.jsonl"))
check("蜂群运行", rr["ok"], str(rr.get("stderr", ""))[:120])
ref = reflect(rr["report"], routes=ROUTES)
check("正常报告：前提破坏 0 项", ref["broken"] == 0, str(ref["broken"]))
check("反思结论=一致", ref["verdict"].startswith("一致"), ref["verdict"])
check("影响面为空", ref["impacts"] == [])
check("断言抽取覆盖 health/gossip/watermark",
      any(c["kind"] == "health" for c in ref["claims"])
      and any(c["kind"] == "gossip" for c in ref["claims"])
      and any(c["kind"] == "watermark" for c in ref["claims"]),
      str(len(ref["claims"])) + " 条断言")

# ============ ② 注入破坏：gossip_consistent=False ============
print("=== ② 注入 gossip 覆盖破坏 ===")
import copy
bad = copy.deepcopy(rr["report"])
bad["gossip_consistent"] = False
ref2 = reflect(bad, routes=ROUTES)
check("前提破坏被检出（broken>0）", ref2["broken"] > 0, str(ref2["broken"]))
check("破坏点含 gossip 覆盖前提",
      any("P2 gossip" in p["premise"] for p in ref2["premises"] if not p["holds"]))
check("影响推演给出 integrity_drop",
      any(i["kind"] == "integrity_drop" for i in ref2["impacts"]),
      str([i["kind"] for i in ref2["impacts"]]))
check("影响面指向乙（gossip 目标入边）",
      any("实例乙" in i["affected"] for i in ref2["impacts"]))

# ============ ③ 注入 error 终态：信任沿用 → 下游受染 ============
print("=== ③ 注入 error 终态（信任沿用推演） ===")
bad3 = copy.deepcopy(rr["report"])
bad3["final_states"]["实例甲"]["error"] = "模拟实例故障"
ref3 = reflect(bad3, routes=ROUTES)
check("error 前提被检出（甲 P1 破）",
      any(not p["holds"] and "P1" in p["premise"]
          and "实例甲" in p["claim"] for p in ref3["premises"]))
check("影响推演 kind=trust_stale（信任沿用受染）",
      any(i["kind"] == "trust_stale" for i in ref3["impacts"]),
      str([i["kind"] for i in ref3["impacts"]]))
check("受染下游含实例乙（甲的 @trust gossip 目标）",
      any("实例乙" in i["affected"] for i in ref3["impacts"] if i["kind"] == "trust_stale"))

# ============ ④ 多跳影响推演：gossip 链式波及 ============
print("=== ④ 多跳影响面（depth=2） ===")
ROUTES4 = ROUTES + [{"from": "实例乙", "event_type": "定向", "to": "实例丙",
                     "payload": "@trust", "level": 0}]
cfg4 = make_swarm_config(
    instances=[
        {"id": "实例甲", "role": "源", "trust": 0.1, "symbols": {"信任值": 0.5}},
        {"id": "实例乙", "role": "中继", "trust": 0.2, "symbols": {"信任值": 0.5}},
        {"id": "实例丙", "role": "端", "trust": 0.2, "symbols": {"信任值": 0.5}},
    ],
    routes=ROUTES4, rounds=2, shared_secret=SECRET)
rr4 = run_swarm(proj, cfg4, wal_path=os.path.join(tmp, "b.jsonl"))
check("三实例运行", rr4["ok"], str(rr4.get("stderr", ""))[:120])
bad4 = copy.deepcopy(rr4["report"])
bad4["final_states"]["实例甲"]["error"] = "模拟故障"
ref4 = reflect(bad4, routes=ROUTES4)  # project_impacts 默认 depth=2
imp4 = [i for i in ref4["impacts"] if i["kind"] == "trust_stale"]
check("两跳影响面：甲破 → 乙（一跳）→ 丙（二跳经乙的定向路由）",
      any("实例乙" in i["affected"] and "实例丙" in i["affected"] for i in imp4),
      str([i["affected"] for i in imp4]))

print(f"\n{pass_n} passed, {fail_n} failed")
sys.exit(1 if fail_n else 0)
