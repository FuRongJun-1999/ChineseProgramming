"""
analyzer.py · 分析器（第六阶段 C4）：字节码可读转储
中文源码/.pbc → 可读指令列表（地址+指令+参数）——开发者工具链。
"""


def bytecode_dump(code):
    """字节码（枚举/字符串 op）→ 可读指令列表"""
    lines = []
    for i, (op, arg) in enumerate(code):
        name = op.name if hasattr(op, "name") else str(op)
        lines.append(f"{i:4d}  {name:14s} {arg}")
    return lines


def analyze_source(source, strict=False):
    """中文源码 → 字节码转储（分析器入口）"""
    from .compiler import compile_source
    code, result = compile_source(source, strict=strict)
    if not result["ok"]:
        return None, result
    return bytecode_dump(code), result


def analyze_pbc(path):
    """.pbc 文件 → 字节码转储"""
    from .pbc import load_pbc
    return bytecode_dump(load_pbc(path))


if __name__ == "__main__":
    print("=== C4：分析器（字节码可读转储）===\n")
    src = """术曰：
1。道 新信任路径；
2。德 0.3；
3。止。
"""
    lines, r = analyze_source(src)
    if r["ok"]:
        for ln in lines:
            print(f"  {ln}")
        print(f"\n=== 判定 ===\n分析器: {'✔ 字节码可读转储' if lines else '✘'}")
