from core.lexer import tokenize
from core.parser import parse_tokens, Parser

source = """若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。"""

tokens, _ = tokenize(source)
ast = parse_tokens(tokens, [])

print('=== AST Statements ===')
for i, stmt in enumerate(ast.statements):
    print(f'  stmt{i}: type={stmt.type.name}, value={stmt.value!r}')
    if hasattr(stmt, 'operands') and stmt.operands:
        for j, op in enumerate(stmt.operands):
            print(f'    op{j}: type={op.type.name}, value={op.value!r}')
    if hasattr(stmt, 'then_body') and stmt.then_body:
        tb = stmt.then_body
        print(f'    then: type={tb.type.name}')
        if hasattr(tb, 'operands'):
            for j, op in enumerate(tb.operands):
                print(f'      op{j}: type={op.type.name}, value={op.value!r}')
    if hasattr(stmt, 'steps'):
        for s in stmt.steps:
            print(f'    step{s.step_num}: {s.statement.type.name if s.statement else "None"}')
            if s.statement and hasattr(s.statement, 'operands'):
                for j, op in enumerate(s.statement.operands):
                    print(f'      op{j}: type={op.type.name}, value={op.value!r}')

print(f'\nTotal statements: {len(ast.statements)}')
print(f'Parser errors: {ast.errors}')
