# -*- coding: utf-8 -*-
"""rust_swarm · 多进程蜂群（RUST-SWARM-REV1 · v0.5）
荣 2026-09-06 裁定：多实例并行（进程级蜂群）+ 消息传递 + 实例私有信任/条件空间 + 聚合层。
对齐 aeis.swarm 语义（事件总线 WAL/ACK/HMAC、trust_aggregator T_avg/T_min/T_variance/
T_alignment、B6 防操纵）。职责：
  make_swarm_config           蜂群配置生成（实例身份/初始环境/路由表）→ swarm.json
  run_swarm                   调 protocol_vm swarm 子命令 → 报告解析
  verify_wal_signatures       WAL HMAC-SHA256 验签（Python hashlib/hmac 独立复核——
                              Rust 侧手写 SHA256 的交叉验证）
  aggregate_trust_python      信任聚合 Python 参照实现（对照 Rust 聚合一致性）
白箱 · 确定性。协调器与实例均为 Rust 进程（多进程隔离）。
"""
from __future__ import annotations
import hashlib
import hmac as _hmac
import json
import os
import subprocess
from typing import Dict, List, Optional

from .rust_codegen import build_rust_exe

ALGO = "rust_swarm-0.1"
DEFAULT_SECRET = "蜂群默认密钥"


def make_swarm_config(instances: List[Dict], routes: Optional[List[Dict]] = None,
                      rounds: int = 1, shared_secret: str = DEFAULT_SECRET) -> Dict:
    """instances: [{"id","role","trust","symbols"}]；routes: [{"from","event_type","to","payload","level"}]
    payload 中 "@trust" 占位符在运行时替换为源实例终态信任值。"""
    return {"algo": ALGO, "shared_secret": shared_secret, "rounds": max(1, int(rounds)),
            "instances": [{"id": i["id"], "role": i.get("role", "worker"),
                           "trust": float(i.get("trust", 0.0)),
                           "symbols": i.get("symbols", {})} for i in instances],
            "routes": [{"from": r["from"], "event_type": r.get("event_type", "消息"),
                        "to": r["to"], "payload": r.get("payload", "null"),
                        "level": int(r.get("level", 0))} for r in (routes or [])]}


def run_swarm(project_dir: str, config: Dict, wal_path: str = "events.jsonl",
              timeout: int = 120) -> Dict:
    """写 swarm.json → protocol_vm swarm → 报告解析（含 WAL 路径回传）。"""
    cfg_path = os.path.join(project_dir, "swarm.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)
    exe = build_rust_exe(project_dir)
    wal_full = os.path.abspath(os.path.join(project_dir, wal_path))
    r = subprocess.run([exe, "swarm", "--config", cfg_path, "--wal", wal_full],
                       capture_output=True, text=True, timeout=timeout,
                       cwd=project_dir)
    if r.returncode != 0:
        return {"ok": False, "stage": "swarm", "stderr": r.stderr[-3000:]}
    try:
        report = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "stage": "parse", "stdout": r.stdout[-2000:]}
    return {"ok": True, "report": report, "wal": wal_full}


def verify_wal_signatures(wal_path: str, shared_secret: str) -> Dict:
    """WAL 逐条验签（Python hmac 独立实现——交叉验证 Rust 手写 SHA256）。
    签名串：type|from|to|round|ts|payload（与 Rust swarm.rs 约定一致）。"""
    ok = bad = 0
    with open(wal_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # payload 在 WAL 里是内嵌 JSON——签名时用原始文本切片保真；
            # 行尾恰有一个 WAL 记录级闭括号需剥掉（payload 文本后面是行闭合 '}'）
            raw = line[line.index('"payload":') + len('"payload":'):]
            raw_payload = raw[:-1] if raw.endswith("}") else raw
            msg = "%s|%s|%s|%s|%s|%s" % (rec["type"], rec["from"], rec["to"],
                                         rec["round"], rec["ts"], raw_payload)
            expect = _hmac.new(shared_secret.encode(), msg.encode(),
                               hashlib.sha256).hexdigest()
            if _hmac.compare_digest(expect, rec["hmac"]):
                ok += 1
            else:
                bad += 1
    return {"total": ok + bad, "verified": ok, "bad": bad,
            "all_valid": bad == 0}


def aggregate_trust_python(trust_values: List[float]) -> Dict:
    """信任聚合 Python 参照（对齐 aeis.swarm.trust_aggregator.snapshot 操作化定义：
    T_alignment = 1 - T_variance / T_avg；值域 0-1 夹取）。"""
    ts = [max(0.0, min(1.0, float(t))) for t in trust_values]
    if not ts:
        return {"T_avg": 0.0, "T_min": 0.0, "T_variance": 0.0, "T_alignment": 0.0}
    n = len(ts)
    avg = sum(ts) / n
    var = sum((t - avg) ** 2 for t in ts) / n
    align = 1.0 - var / avg if avg > 0 else 0.0
    return {"T_avg": avg, "T_min": min(ts), "T_variance": var, "T_alignment": align}
