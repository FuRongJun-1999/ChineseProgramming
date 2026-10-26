# -*- coding: utf-8 -*-
"""#8 / #5 守卫：`知足` 的非数值操作数必须在编译期给出**干净编译错误**。

背景（issue #8）：`core/compiler.py::_instr` 里 `德` 分支对非数值操作数有
`try/except` 守卫（抛 `SyntaxError` → 干净的「编译错误: …」），而相隔 12 行的
`知足`(ZHIZU) 分支直接 `float(val)` ⇒ 用户看到的是 Python 栈（`ValueError:
could not convert string to float: '值'`），不是编译错误。

同源半边（issue #5）：`check` 判该文件通过、`compile-pbc` 判编译错误——同一 CLI
对同一份源码结论相反，且相反的那一侧是**崩**而不是拒绝。

本守卫钉住：
  ① `知足 <标识符>` ⇒ 干净的编译错误（含「名实不符」），**无 Python traceback**；
  ② 与 `德 <标识符>` 的错误文案形状一致（同一函数内两条路同口径）；
  ③ 合法数值操作数不受影响（`知足 0.5；` 正常编译出指令）。

判别力（`--mutate`）：把新增的 `try/except` 换回裸 `float(val)`（等价回退本修复）
⇒ 断言①必红（`ValueError` 逃逸）。

运行：
  python -X utf8 -m pytest tests/test_issue8_zhizu_operand_guard.py -q
  python -X utf8 tests/test_issue8_zhizu_operand_guard.py
  python -X utf8 tests/test_issue8_zhizu_operand_guard.py --mutate
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

_RP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RP)

PASS = FAIL = 0

# 正确段名是 `术曰：`（`未更：` 段的语句会被解析器静默跳过——那是另一条口径，
# 不在本件范围；本守卫用官方样例同款段名，见 compiler/tests/test_compiler_c2.py src1）。
def _src(body: str) -> str:
    return "问曰：如何验证信任？\n答曰：信任值大于0.7。\n术曰：\n" + body


def _run_cli(src_text: str) -> tuple:
    d = tempfile.mkdtemp(prefix="i8_")
    p = os.path.join(d, "t.proto")
    with open(p, "w", encoding="utf-8") as f:
        f.write(src_text)
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "cli", "compile-pbc",
                        p, "-o", os.path.join(d, "out")],
                       capture_output=True, text=True, cwd=_RP)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _ok(cond, label, detail=""):
    global PASS, FAIL
    PASS += int(bool(cond)); FAIL += int(not cond)
    print(f'[{"✓" if cond else "✘"}] {label}' + (f"  · {detail}" if detail else ""))


def test_zhizu_identifier_gives_clean_error():
    rc, out = _run_cli(_src("1。知足 值；\n2。止。\n"))
    _ok("编译错误" in out, "知足 标识符 → 干净编译错误", out.strip().splitlines()[-1][:70] if out.strip() else "")
    _ok("名实不符" in out, "含「名实不符」判据词")
    _ok("Traceback" not in out and "ValueError" not in out,
         "无 Python 栈逃逸（修前为 ValueError 裸崩）")


def test_de_and_zhizu_error_shape_consistent():
    _, out_de = _run_cli(_src("1。德 值；\n2。止。\n"))
    _, out_z = _run_cli(_src("1。知足 值；\n2。止。\n"))
    _ok(("德 的操作数必须是数值" in out_de) and ("知足 的操作数必须是数值" in out_z),
         "德 / 知足 两条路的错误形状一致（同函数同口径）")


def test_zhizu_numeric_still_compiles():
    rc, out = _run_cli(_src("1。知足 0.5；\n2。止。\n"))
    _ok(rc == 0 and "原生编译" in out, "知足 0.5 → 正常编译（合法路径不受影响）", out.strip()[-60:])


def _run_all() -> int:
    global FAIL
    before = FAIL
    for fn in (test_zhizu_identifier_gives_clean_error,
               test_de_and_zhizu_error_shape_consistent,
               test_zhizu_numeric_still_compiles):
        try:
            fn()
        except Exception as ex:  # 子进程/文件系统异常也算失败
            FAIL += 1
            print(f"[✘] {fn.__name__}: {type(ex).__name__}: {ex}")
    return FAIL - before


def main(argv) -> int:
    if "--mutate" in argv:
        # 变异：把 `知足` 分支的 try/except 换回裸 float(val)（等价回退本修复）
        comp = os.path.join(_RP, "core", "compiler.py")
        with open(comp, encoding="utf-8") as f:
            orig = f.read()
        guarded = '''            try:
                threshold = float(val) if val is not None else 0.0
            except (TypeError, ValueError):
                raise SyntaxError(
                    f"L{s.line} 知足 的操作数必须是数值，得到 '{val}'（名实不符）")'''
        bare = '''            threshold = float(val) if val is not None else 0.0'''
        if guarded not in orig:
            print("变异锚点未找到——守卫可能已改形状，请复核")
            return 2
        try:
            with open(comp, "w", encoding="utf-8") as f:
                f.write(orig.replace(guarded, bare, 1))
            bad = _run_all()
            print(f"#8 守卫（变异态）：失败 {bad} 条")
            return 0 if bad >= 1 else 1
        finally:
            with open(comp, "w", encoding="utf-8") as f:
                f.write(orig)
    bad = _run_all()
    print(f"#8 守卫：{PASS} 通过 / {bad} 失败")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
