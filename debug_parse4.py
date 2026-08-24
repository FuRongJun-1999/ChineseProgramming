from core.lexer import tokenize
from core.parser import Parser

source = """若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。"""

tokens, _ = tokenize(source)
parser = Parser(tokens, [])

# 直接调用 parse()
ast = parser.parse()

print('=== parse() result ===')
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
            sm = s.statement
            print(f'    step{s.step_num}: {sm.type.name if sm else "None"}')
            if sm and hasattr(sm, 'operands'):
                for j, op in enumerate(sm.operands):
                    print(f'      op{j}: type={op.type.name}, value={op.value!r}')
            elif sm:
                print(f'      value={sm.value!r}')

print(f'\nTotal: {len(ast.statements)}')
print(f'Parser errors: {parser.errors}')
