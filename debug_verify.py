from core.lexer import tokenize
from core.parser import Parser, TokenType

source = """道 新信任路径
问曰：如何验证信任？"""

tokens, _ = tokenize(source)

# 只测试 _parse_instruction 返回后主循环的行为
parser = Parser(tokens, [])

# 手动模拟主循环，但打印每个细节
iter_count = 0
while not parser._is_at_end():
    ct = parser.current_token
    print(f"[iter {iter_count}] current: {ct}")
    
    if parser._match(TokenType.NEWLINE, TokenType.SEMICOLON, TokenType.COMMA):
        print(f"  → matched newline/sep, continue")
        iter_count += 1
        continue
    
    # 调用 _parse_statement
    stmt = parser._parse_statement()
    
    if stmt:
        print(f"  → stmt: type={stmt.type.name} value={stmt.value!r}")
        if hasattr(stmt, 'operands') and stmt.operands:
            for j, op in enumerate(stmt.operands):
                print(f"    op{j}: {op.type.name} value={op.value!r}")
        if hasattr(stmt, 'then_body') and stmt.then_body:
            tb = stmt.then_body
            print(f"    then: {tb.type.name}")
            if hasattr(tb, 'operands'):
                for j, op in enumerate(tb.operands):
                    print(f"      op{j}: {op.type.name} value={op.value!r}")
        # 这是关键：模拟 program.add_statement(stmt)
        print(f"  [would add to program: type={stmt.type.name}]")
    else:
        print(f"  → None")
    
    # 检查循环条件
    ct2 = parser.current_token
    print(f"  after: {ct2}")
    print()
    iter_count += 1
    if iter_count > 10:
        break

# 现在用真正的 parse() 看结果
print("=== Real parse() ===")
tokens2, _ = tokenize(source)
parser2 = Parser(tokens2, [])
ast = parser2.parse()
print(f"Total statements: {len(ast.statements)}")
for i, stmt in enumerate(ast.statements):
    print(f"  stmt{i}: type={stmt.type.name} value={stmt.value!r}")
    if hasattr(stmt, 'operands') and stmt.operands:
        for j, op in enumerate(stmt.operands):
            print(f"    op{j}: {op.type.name} value={op.value!r}")
