from core.lexer import tokenize
from core.parser import Parser

source = """若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。"""

tokens, _ = tokenize(source)
parser = Parser(tokens, [])

# 直接跟踪 parse() 主循环
program = None
print("=== Manual parse() loop ===")
count = 0
while not parser._is_at_end():
    tok = parser.current_token
    tok_info = f"{tok.type.name} value={tok.value!r}" if tok else "EOF"
    
    # 调用 _parse_statement
    stmt = parser._parse_statement()
    
    if stmt:
        res_info = f"{stmt.type.name} value={stmt.value!r}"
        extra = ""
        if hasattr(stmt, 'operands') and stmt.operands:
            ops = [(op.type.name, op.value) for op in stmt.operands]
            extra = f" ops={ops}"
        if hasattr(stmt, 'then_body') and stmt.then_body:
            tb = stmt.then_body
            extra += f" then={tb.type.name}"
            if hasattr(tb, 'operands'):
                ops = [(op.type.name, op.value) for op in tb.operands]
                extra += f" then_ops={ops}"
        print(f"  [{count}] at {tok_info} → {res_info}{extra}")
    else:
        print(f"  [{count}] at {tok_info} → None")
    
    count += 1

print(f"\nTotal loop iterations: {count}")
print(f"Program statements: {len(parser.parse().statements)}")
# 重新parse获取结果
tokens2, _ = tokenize(source)
parser2 = Parser(tokens2, [])
ast = parser2.parse()
print(f"AST statements ({len(ast.statements)}):")
for i, stmt in enumerate(ast.statements):
    print(f"  stmt{i}: {stmt.type.name} value={stmt.value!r}")
    if hasattr(stmt, 'operands') and stmt.operands:
        for j, op in enumerate(stmt.operands):
            print(f"    op{j}: {op.type.name} value={op.value!r}")
    if hasattr(stmt, 'then_body') and stmt.then_body:
        tb = stmt.then_body
        print(f"    then: {tb.type.name}")
        if hasattr(tb, 'operands'):
            for j, op in enumerate(tb.operands):
                print(f"      op{j}: {op.type.name} value={op.value!r}")
    if hasattr(stmt, 'steps'):
        for s in stmt.steps:
            sm = s.statement
            print(f"    step{s.step_num}: {sm.type.name if sm else 'None'}")
            if sm and hasattr(sm, 'operands'):
                for j, op in enumerate(sm.operands):
                    print(f"      op{j}: {op.type.name} value={op.value!r}")
            elif sm:
                print(f"      value={sm.value!r}")
