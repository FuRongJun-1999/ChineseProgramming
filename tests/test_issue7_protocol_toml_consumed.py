# -*- coding: utf-8 -*-
"""#7 守卫：`protocol.toml` 必须被真正消费（`cli init` 标为「项目配置」却零读取点）。

背景（issue #7）：`python -m cli init` 写出 `protocol.toml` 并在提示里标为
「📄 protocol.toml —— 项目配置」，但全仓**零读取点**——用户改 `[compiler] strict`
或 `llm_assist` 不产生任何效果（配置文件是死的）。

本守卫钉住（结构面，可机械复核）：
  ① `_load_project_config` 能从源文件上溯找到 `protocol.toml` 并解析三项；
  ② 找不到配置时返回 `{}`（不报错——`cli init` 之外的项目属正常）；
  ③ 两个编译入口确实调用它（源码级断言：`cmd_compile` / `cmd_compile_pbc`
     函数体内出现 `_load_project_config(`）。

**边界（如实声明）**：`[compiler] strict` 的**行为级**差异未在本守卫里断言——
`compile_source(strict=…)` 只拦 `name_errors`，而现有 `NameChecker` 对未声明读取
不产出 error（那是另一条独立缺陷），故本仓库当前**构造不出** strict 真/假可判别
的样例。本守卫因此只钉「配置被读到并接到调用点」这一层，不冒充行为级验证。

运行：
  python -X utf8 -m pytest tests/test_issue7_protocol_toml_consumed.py -q
  python -X utf8 tests/test_issue7_protocol_toml_consumed.py
"""
from __future__ import annotations

import inspect
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


def _project(tmp, strict="true", llm="false"):
    os.makedirs(os.path.join(tmp, "src"), exist_ok=True)
    with open(os.path.join(tmp, "protocol.toml"), "w", encoding="utf-8") as f:
        f.write('[compiler]\nstrict = %s\nllm_assist = %s\n\n[runtime]\npath = "./rt"\n'
                % (strict, llm))
    src = os.path.join(tmp, "src", "main.proto")
    with open(src, "w", encoding="utf-8") as f:
        f.write("问曰：q\n答曰：a\n术曰：\n1。德 0.5；\n2。止。\n")
    return src


def test_config_parsed_from_project_root():
    from cli import _load_project_config
    tmp = tempfile.mkdtemp(prefix="i7_")
    src = _project(tmp, strict="true", llm="false")
    cfg = _load_project_config(src)
    _ok(cfg.get("strict") is True, "解析 [compiler] strict=true", str(cfg))
    _ok(cfg.get("llm_assist") is False, "解析 [compiler] llm_assist=false")
    _ok(cfg.get("runtime_path") == "./rt", "解析 [runtime] path")


def test_strict_false_is_parsed_as_false():
    from cli import _load_project_config
    tmp = tempfile.mkdtemp(prefix="i7b_")
    src = _project(tmp, strict="false", llm="true")
    cfg = _load_project_config(src)
    _ok(cfg.get("strict") is False, "strict=false 解析为 False（不是真值串）", str(cfg))
    _ok(cfg.get("llm_assist") is True, "llm_assist=true 解析为 True")


def test_missing_config_returns_empty():
    from cli import _load_project_config
    tmp = tempfile.mkdtemp(prefix="i7c_")
    src = os.path.join(tmp, "main.proto")
    with open(src, "w", encoding="utf-8") as f:
        f.write("术曰：1。止。\n")
    _ok(_load_project_config(src) == {}, "无 protocol.toml ⇒ 返回 {} 且不抛")


def test_both_compile_entries_call_config_loader():
    import cli
    for fn_name in ("cmd_compile", "cmd_compile_pbc"):
        fn = getattr(cli, fn_name, None)
        _ok(fn is not None, f"{fn_name} 存在")
        if fn is None:
            continue
        src = inspect.getsource(fn)
        _ok("_load_project_config(" in src,
             f"{fn_name} 内调用 _load_project_config（配置真被消费）")


def _run_all() -> int:
    global FAIL
    before = FAIL
    for fn in (test_config_parsed_from_project_root,
               test_strict_false_is_parsed_as_false,
               test_missing_config_returns_empty,
               test_both_compile_entries_call_config_loader):
        try:
            fn()
        except Exception as ex:
            FAIL += 1
            print(f"[✘] {fn.__name__}: {type(ex).__name__}: {ex}")
    return FAIL - before


def main(argv) -> int:
    bad = _run_all()
    print(f"#7 守卫：{PASS} 通过 / {bad} 失败")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
