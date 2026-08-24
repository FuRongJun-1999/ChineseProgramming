from core.lexer import tokenize
from core.parser import parse_tokens, Parser

source = """若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。"""

tokens, _ = tokenize(source)
parser = Parser(tokens, [])
ast = parser.parse()

print(f"Total statements: {len(ast.statements)}")
print()
for i, stmt in enumerate(ast.statements):
    print(f"stmt{i}:")
    print(f"  type={stmt.type}")
    print(f"  type.name={stmt.type.name}")
    print(f"  value={stmt.value!r}")
    print(f"  line={stmt.line}, col={stmt.column}")
    print(f"  children count={len(stmt.children)}")
    for j, child in enumerate(stmt.children):
        print(f"    child{j}: type={child.type.name} value={child.value!r}")
    print()
