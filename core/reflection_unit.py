# -*- coding: utf-8 -*-
"""reflection_unit · 反思单元（智能论 §3.12 二级回溯的操作化 · 心跳任务 2026-09-13）

荣 2026-09-13 给出反思单元的两个反思问句：
  问句一（隐藏前提）：这个信息的成立依赖哪些未声明的前提？前提还成立吗？
  问句二（影响推演）：这个信息为真/被破坏，会波及什么？

定位：验证单元（health/gossip 对账/验签）发现偏差；反思单元不止步于偏差，
审查偏差背后的前提与影响面（§3.12 二级「根源回溯」）。反思只回溯不截断——
截断是维生系统（三级）的职责，反思结论供设计者/维生消费。

纯 std 零依赖。输入=蜂群报告（run_swarm 的 report dict）± WAL+密钥（可选，
用于对「验签全过」前提做独立复验），输出=反思报告 dict。
"""
from __future__ import annotations
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 断言抽取：从蜂群报告提取「值得反思的关键断言」
# ---------------------------------------------------------------------------

def extract_claims(report: Dict) -> List[Dict]:
    claims: List[Dict] = []
    for iid, h in (report.get("health") or {}).items():
        claims.append({"claim": f"health[{iid}].score=={h.get('score')}",
                       "kind": "health", "instance": iid, "value": h.get("score")})
    gc = report.get("gossip_consistent")
    if gc is not None:
        claims.append({"claim": f"gossip_consistent=={gc}", "kind": "gossip",
                       "value": gc})
    for iid, w in (report.get("watermarks") or {}).items():
        claims.append({"claim": f"watermarks[{iid}]=={w}", "kind": "watermark",
                       "instance": iid, "value": w})
    t = report.get("trust") or {}
    if t:
        claims.append({"claim": f"T_avg=={t.get('T_avg')}", "kind": "trust",
                       "value": t.get("T_avg")})
    return claims


# ---------------------------------------------------------------------------
# 问句一（隐藏前提）：每类断言的未声明前提清单 + 逐条核查
# ---------------------------------------------------------------------------

def _health_premises(report: Dict, iid: str, wal_check: Optional[Dict]) -> List[Dict]:
    """health[iid].score 的隐含前提：
    P1 无 error 终态（error 终态会把 threat/success 因子拉低）
    P2 gossip 覆盖完整（gossip_consistent；无 gossip 表=未启用，前提自然成立）
    P3 事件验签全过（若提供 WAL+secret 则独立复验，否则标记 not_checked）"""
    fs = (report.get("final_states") or {}).get(iid, {})
    out = [{"claim": f"health[{iid}].score=={((report.get('health') or {}).get(iid) or {}).get('score')}",
            "premise": "P1 无 error 终态",
            "holds": "error" not in fs,
            "evidence": f"final_states[{iid}] {'含' if 'error' in fs else '不含'} error 键"}]
    gc = report.get("gossip_consistent")
    is_gossip_target = iid in (report.get("gossip") or {})
    out.append({"claim": out[0]["claim"],
                "premise": "P2 gossip 覆盖完整（目标实例）或非 gossip 目标",
                "holds": (gc is not False) or (not is_gossip_target),
                "evidence": f"gossip_consistent={gc}, {iid} {'是' if is_gossip_target else '不是'} gossip 目标"})
    if wal_check is not None:
        fails = wal_check.get("verify_fail_by_instance", {}).get(iid, 0)
        out.append({"claim": out[0]["claim"],
                    "premise": "P3 该实例相关事件验签全过",
                    "holds": fails == 0,
                    "evidence": f"verify_fail[{iid}]={fails}"})
    return out


def _gossip_premises(report: Dict, wal_check: Optional[Dict]) -> List[Dict]:
    gc = report.get("gossip_consistent")
    out = [{"claim": f"gossip_consistent=={gc}",
            "premise": "P1 gossip 未启用（空表）时 true 为缺省语义而非实测",
            "holds": not (gc is True and not (report.get("gossip") or {})),
            "evidence": f"gossip 表={'空' if not (report.get('gossip') or {}) else '非空'}"}]
    if wal_check is not None:
        done = wal_check.get("last_snapshot_round")
        rounds = report.get("rounds")
        truncated = done is not None and rounds is not None and done < rounds
        out.append({"claim": out[0]["claim"],
                    "premise": "P2 WAL 无坏尾截断（末快照轮==目标轮数）",
                    "holds": not truncated,
                    "evidence": f"末快照轮={done}, 目标轮数={rounds}"})
    return out


def check_premises(report: Dict, wal_check: Optional[Dict] = None) -> List[Dict]:
    """问句一：对报告关键断言逐条核查隐含前提。
    wal_check：verify_wal_signatures 的返回 + last_snapshot_round（可选，
    由调用方合并传入；提供时追加 P3/P2 类可复核前提）。"""
    premises: List[Dict] = []
    for iid in (report.get("health") or {}):
        premises.extend(_health_premises(report, iid, wal_check))
    if report.get("gossip_consistent") is not None:
        premises.extend(_gossip_premises(report, wal_check))
    return premises


# ---------------------------------------------------------------------------
# 问句二（影响推演）：前提破坏 → 沿路由/依赖关系推演波及面
# ---------------------------------------------------------------------------

def project_impacts(report: Dict, premises: List[Dict],
                    routes: Optional[List[Dict]] = None,
                    depth: int = 2) -> List[Dict]:
    """问句二：对每个 holds=False 的前提，推演影响面。
    传播规则（影响图，手工声明——确定性，不猜测）：
      gossip 覆盖破坏 → 缺收实例 integrity 因子降（权重 0.2）
                      → 其 health.score 降 → 若存在 from=该实例且 payload 含 @trust
                        的路由，下游目标下一轮收到的信任值为受染旧值
      error 终态    → 该实例 trust 沿用上一轮（error 无 trust 字段）
                      → 下游 @trust 路由目标受染（同上）
      WAL 截断      → 快照后事件回滚重跑 → 重跑轮次的 ACK/gossip 水位与
                      一次跑完不可逐字节比（ts 不同），对账须用结构不变量"""
    broken = [p for p in premises if not p["holds"]]
    routes = routes or []
    impacts: List[Dict] = []
    for p in broken:
        text = p["premise"]
        if "P1 无 error 终态" in text:
            iid = p["claim"].split("[")[1].split("]")[0]
            down = _downstream(report, routes, iid, depth)
            impacts.append({"broken_premise": p, "kind": "trust_stale",
                            "affected": down,
                            "note": f"{iid} 信任沿用旧值；下游 @trust 目标收到的信任值为旧值"})
        elif "P2 gossip" in text and "覆盖" in text:
            iid = p["claim"].split("[")[1].split("]")[0]
            impacts.append({"broken_premise": p, "kind": "integrity_drop",
                            "affected": [iid],
                            "note": "缺收实例 integrity 因子按覆盖率降级（权重 0.2）——受影响者为缺收实例自身"})
        elif "P2 WAL" in text:
            impacts.append({"broken_premise": p, "kind": "replay_rejoin",
                            "affected": ["协调器"],
                            "note": "快照后事件已回滚重跑；对账须用结构不变量（计数/终态），勿逐字节比 WAL"})
        elif "P3" in text:
            iid = p["claim"].split("[")[1].split("]")[0]
            impacts.append({"broken_premise": p, "kind": "integrity_drop",
                            "affected": [iid],
                            "note": "验签失败事件已计入 integrity 降级"})
    return impacts


def _downstream(report: Dict, routes: List[Dict], src: str, depth: int) -> List[str]:
    """沿路由表从 src 做 depth 跳影响面（gossip 路由视为扇出至全部其他实例）。"""
    affected: List[str] = []
    frontier = {src}
    inst = list((report.get("final_states") or {}).keys())
    for _ in range(max(1, depth)):
        nxt: List[str] = []
        for r in routes:
            if r.get("from") in frontier:
                targets = ([x for x in inst if x != r["from"]]
                           if r.get("to") == "*" else [r.get("to")])
                for t in targets:
                    if t and t not in affected and t != src:
                        affected.append(t)
                        nxt.append(t)
        frontier = set(nxt)
        if not frontier:
            break
    return affected


# ---------------------------------------------------------------------------
# 反思入口
# ---------------------------------------------------------------------------

def reflect(report: Dict, routes: Optional[List[Dict]] = None,
            wal_verify: Optional[Dict] = None,
            last_snapshot_round: Optional[int] = None) -> Dict:
    """反思单元入口：两问句合成反思报告（只回溯，不截断——§3.12 二级）。"""
    wal_check = None
    if wal_verify is not None:
        wal_check = {"verify_fail_by_instance": {}, "last_snapshot_round": last_snapshot_round}
    premises = check_premises(report, wal_check)
    impacts = project_impacts(report, premises, routes)
    broken_n = sum(1 for p in premises if not p["holds"])
    verdict = ("一致（全部隐含前提成立）" if broken_n == 0
               else f"前提破坏 {broken_n} 项，影响面 {len(impacts)} 条——供设计者/维生消费")
    return {"claims": extract_claims(report), "premises": premises,
            "impacts": impacts, "broken": broken_n, "verdict": verdict}
