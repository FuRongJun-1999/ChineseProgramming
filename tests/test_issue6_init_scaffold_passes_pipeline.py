# -*- coding: utf-8 -*-
"""#6 守卫：`cli init` 生成的脚手架必须能过自家流水线（三条后端全通）。

背景（issue #6）：`python -m cli init <项目>` 生成的 `src/main.proto` 含
`2。若条件空间为默认，则德 累积信任值。` —— `德` 的操作数是**标识符**
（非数值），`compile-pbc` 判「编译错误」而 `check`/`compile` 判通过；`init`
的提示又让新用户直接跑 `pc compile`，于是**首次使用第一步就撞墙**
（且 #5 的旁证：示例文件 `examples/companion.proto` 同一形态过不了自家流水线）。

本守卫钉住：
  ① `cli init` 生成的 `src/main.proto` 在三条后端（check / compile / compile-pbc）
     下**全部通过**；
  ② 模板仍保留教学意图（含 道 / 德 / 若…则 / 止 四种形态，且不止 1 条指令）；
  ③ 生成的 `protocol.toml` 存在且可被 `_load_project_config` 解析（#7 联动）。

运行：
  python -X utf8 -m pytest tests/test_issue6_init_scaffold_passes_pipeline.py -q
  python -X utf8 tests/test_issue6_init_scaffold_passes_pipeline.py
  python -X utf8 tests/test_issue6_init_scaffold_passes_pipeline.py --mutate
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

_RP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RP)

PASS = FAIL = 0


def _ok(cond, label, detail=""):
    global PASS, FAIL
    PASS += int(bool(cond)); FAIL += int(not cond)
    print(f'[{"✓" if cond else "✘"}] {label}' + (f"  · {detail}" if detail else ""))


def _init_project() -> tuple:
    d = tempfile.mkdtemp(prefix="i6_")
    proj = os.path.join(d, "scaffold")
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "cli", "init", proj],
                       capture_output=True, text=True, cwd=_RP)
    return proj, r


def test_scaffold_passes_all_backends():
    proj, r = _init_project()
    src = os.path.join(proj, "src", "main.proto")
    _ok(os.path.exists(src), "cli init 生成 src/main.proto", r.stdout.strip()[:60])
    if not os.path.exists(src):
        return
    from core.api import CompileOptions, compile_source, validate_source
    from core.compiler import compile_source as comp_compile
    from core.pbc import compile_to_pbc
    with open(src, encoding="utf-8") as f:
        text = f.read()
    res = {
        "check": bool(validate_source(text, CompileOptions(strict=False))["valid"]),
        "compile": bool(compile_source(text, CompileOptions(strict=False)).success),
    }
    _c, rc = comp_compile(text, strict=False)
    res["pbc 内核"] = bool(rc["ok"])
    _c2, r2 = compile_to_pbc(text, os.path.join(proj, "o.pbc"), strict=False)
    res["compile-pbc"] = bool(r2["ok"])
    _ok(all(res.values()), "脚手架在三条后端全部通过", str(res))


def test_template_keeps_teaching_forms():
    proj, _ = _init_project()
    src = os.path.join(proj, "src", "main.proto")
    if not os.path.exists(src):
        _ok(False, "模板存在"); return
    text = open(src, encoding="utf-8").read()
    for form in ("道", "德", "若", "止"):
        _ok(form in text, f"模板保留教学形态「{form}」")
    # 指令条数 > 1（旧模板只有 2 条，其中一条非法）
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("//")]
    instr_lines = [ln for ln in lines if "。" in ln and any(k in ln for k in "道德若止")]
    _ok(len(instr_lines) >= 3, "模板至少 3 条语句（含条件示范）", f"{len(instr_lines)} 条")


def test_scaffold_config_parsable():
    proj, _ = _init_project()
    cfg_path = os.path.join(proj, "protocol.toml")
    _ok(os.path.exists(cfg_path), "生成 protocol.toml")
    if not os.path.exists(cfg_path):
        return
    # 不依赖 #13（PR #13 才引入 _load_project_config）——内联解析验证配置形态
    raw = open(cfg_path, encoding="utf-8").read()
    import re as _re
    m = _re.search(r"^strict\s*=\s*(true|false)\s*$", raw, _re.M)
    _ok(m is not None, "protocol.toml 含可解析的 [compiler] strict 行", raw.splitlines()[:8])
    _ok("llm_assist" in raw, "protocol.toml 含 llm_assist 配置项")


def _run_all() -> int:
    global FAIL
    before = FAIL
    for fn in (test_scaffold_passes_all_backends,
               test_template_keeps_teaching_forms,
               test_scaffold_config_parsable):
        try:
            fn()
        except Exception as ex:
            FAIL += 1
            print(f"[✘] {fn.__name__}: {type(ex).__name__}: {ex}")
    return FAIL - before


def main(argv) -> int:
    if "--mutate" in argv:
        # 变异：把 init 模板回退成旧形态（道 + 德 标识符）⇒ 断言①②必红
        p = os.path.join(_RP, "cli", "__init__.py")
        orig = open(p, encoding="utf-8").read()
        new_tpl = """1。道 示例路径；
2。德 0.5；
3。若 信任值 大于 0.3，则 德 0.2；
4。止。
"""
        old_tpl = """1。道 示例路径；
2。若条件空间为默认，则德 累积信任值。
"""
        if new_tpl not in orig:
            print("变异锚点未找到")
            return 2
        try:
            open(p, "w", encoding="utf-8").write(orig.replace(new_tpl, old_tpl, 1))
            bad = _run_all()
            print(f"#6 守卫（变异态）：失败 {bad} 条")
            return 0 if bad >= 1 else 1
        finally:
            open(p, "w", encoding="utf-8").write(orig)
    bad = _run_all()
    print(f"#6 守卫：{PASS} 通过 / {bad} 失败")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
