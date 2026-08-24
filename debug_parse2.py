from core.lexer import tokenize
from core.parser import Parser

source = """若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。"""

tokens, _ = tokenize(source)
parser = Parser(tokens, [])

# 手动驱动 parse() 主循环
i = 0
while not parser._is_at_end():
    tok = parser.current_token
    print(f'--- Loop {i} ---')
    print(f'  Current: {tok}')
    stmt = parser._parse_statement()
    if stmt:
        print(f'  → {stmt.type.name} value={stmt.value!r}')
        if hasattr(stmt, 'operands'):
            for j, op in enumerate(stmt.operands):
                print(f'    op{j}: {op.type.name} value={op.value!r}')
        if hasattr(stmt, 'then_body') and stmt.then_body:
            tb = stmt.then_body
            print(f'    then: {tb.type.name}')
            if hasattr(tb, 'operands'):
                for j, op in enumerate(tb.operands):
                    print(f'      op{j}: {op.type.name} value={op.value!r}')
    else:
        print(f'  → None')
    print(f'  After: {parser.current_token}')
    i += 1
    print()
