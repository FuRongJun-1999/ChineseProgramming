# -*- coding: utf-8 -*-
"""#5 扩充守卫：`compile` 生成的 Python 代码必须**语法合法且可导入**。

背景（本守卫在修 #5 时发现的新缺陷）：`CodeGenerator` 生成的可执行代码里混入了
三处非代码内容——

  ① 指令行前缀 `  →  `（U+2192）：旧实现 `self._writeln(f"  →  {code}")`
     ⇒ 生成物含箭头，`ast.parse` 报 `invalid character '→' (U+2192)`；
     官方示例 `examples/trust.proto` 生成的 17 行指令**全部不可执行**，
     而 CLI 照报「✅ 编译成功」。
  ② 指令注释与代码同行：`_write(f"# {指令名}")` 不换行，随后 `_writeln(code)`
     接到同一行 ⇒ `    :# 德（累积信任）`。
  ③ 条件行被拆成两行：`_write("if ")` + 表达式 + `_writeln(":")` 在上一行以
     换行结尾时生成 `# 步骤 3if 信任值 > 0.2` 与孤立的 `    :`。

三者叠加使**所有含指令的协议**生成的 Python 都不可执行——而 `compile` 的返回码
是 0、提示是「✅ 编译成功」。本守卫钉住：官方示例生成物 `ast.parse` 通过，
且不含 U+2192。

运行：
  python -X utf8 -m pytest tests/test_issue5_generated_code_executable.py -q
  python -X utf8 tests/test_issue5_generated_code_executable.py
  python -X utf8 tests/test_issue5_generated_code_executable.py --mutate
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile

_RP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RP)

PASS = FAIL = 0


def _ok(cond, label, detail=""):
    global PASS, FAIL
    PASS += int(bool(cond)); FAIL += int(not cond)
    print(f'[{"✓" if cond else "✘"}] {label}' + (f"  · {detail}" if detail else ""))


def _compile_to_py(src_text: str) -> str:
    from core.api import CompileOptions, compile_source
    r = compile_source(src_text, CompileOptions(strict=False))
    assert r.success, f"编译失败: {r.errors[:2]}"
    return r.code


def test_official_example_generates_valid_python():
    p = os.path.join(_RP, "examples", "trust.proto")
    with open(p, encoding="utf-8-sig") as f:   # 官方示例带 UTF-8 BOM
        src = f.read()
    code = _compile_to_py(src)
    try:
        ast.parse(code)
        ok = True
        err = ""
    except SyntaxError as ex:
        ok = False
        err = f"{ex.msg} @L{ex.lineno}: {ex.text.strip()[:50] if ex.text else ''}"
    _ok(ok, "examples/trust.proto 生成物 ast.parse 通过", err)


def test_generated_code_has_no_arrow_glyph():
    p = os.path.join(_RP, "examples", "trust.proto")
    with open(p, encoding="utf-8-sig") as f:
        code = _compile_to_py(f.read())
    _ok("→" not in code, "生成物不含 U+2192 箭头（装饰前缀不得写进代码）")
    _ok("\u2192" not in code, "生成物不含转义形式箭头")


def test_instruction_lines_are_own_lines():
    src = "问曰：q\n答曰：a\n术曰：\n1。德 0.5；\n2。止。\n"
    code = _compile_to_py(src)
    for ln in code.splitlines():
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            continue
        _ok("#" not in stripped or stripped.index("#") > stripped.index("(") if "(" in stripped else True,
             f"代码行不混入注释标记: {stripped[:40]}")
        break
    ast.parse(code)   # 整份可解析即说明行结构合法


def test_condition_line_not_split():
    src = "问曰：q\n答曰：a\n术曰：\n1。德 0.5；\n2。若 信任值 大于 0.3，则 德 0.2；\n3。止。\n"
    code = _compile_to_py(src)
    try:
        ast.parse(code)
        ok, err = True, ""
    except SyntaxError as ex:
        ok, err = False, f"{ex.msg} @L{ex.lineno}"
    _ok(ok, "含条件语句的协议生成物可解析（条件行未被拆成两行）", err)
    _ok("if " in code, "生成物确实含 if 条件行（条件未被吞掉）")


def _run_all() -> int:
    global FAIL
    before = FAIL
    for fn in (test_official_example_generates_valid_python,
               test_generated_code_has_no_arrow_glyph,
               test_instruction_lines_are_own_lines,
               test_condition_line_not_split):
        try:
            fn()
        except Exception as ex:
            FAIL += 1
            print(f"[✘] {fn.__name__}: {type(ex).__name__}: {ex}")
    return FAIL - before


def main(argv) -> int:
    if "--mutate" in argv:
        import core.codegen as cg
        orig = cg.CodeGenerator._gen_instruction
        # 变异：把指令行改回旧形态（箭头前缀 + 注释不换行）⇒ 断言①②必红
        def _old_gen(self, stmt):
            instr_name = cg.INSTRUCTION_NAMES.get(stmt.instruction, "未知指令")
            self._write(f"# {instr_name}")
            code = cg.INSTRUCTION_MAP.get(stmt.instruction, "# 未知指令: {args}").format(args="")
            self._writeln(f"  →  {code}")
        cg.CodeGenerator._gen_instruction = _old_gen
        try:
            bad = _run_all()
            print(f"#5 生成物守卫（变异态）：失败 {bad} 条")
            return 0 if bad >= 2 else 1
        finally:
            cg.CodeGenerator._gen_instruction = orig
    bad = _run_all()
    print(f"#5 生成物守卫：{PASS} 通过 / {bad} 失败")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
