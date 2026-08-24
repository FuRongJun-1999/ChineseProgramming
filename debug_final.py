from core.lexer import tokenize
from core.parser import Parser

source = """若条件空间为伴侣，则止情感权重于0.15。
道 新信任路径
问曰：如何验证信任？
答曰：信任值大于0.7。
术曰：1。德 累积信任值；2。自然 恢复默认。"""

tokens, _ = tokenize(source)
parser = Parser(tokens, [])

# 逐步执行 parse() 主循环，但详细跟踪 _parse_instruction 内部
loop_count = 0
while not parser._is_at_end():
    tok = parser.current_token
    tok_info = f"{tok.type.name} value={tok.value!r}" if tok else "EOF"
    print(f"--- Loop {loop_count}: current={tok_info} ---")
    
    # 如果是道指令，手动跟踪内部
    if tok and tok.type.name == 'DAO':
        print(f"  → Calling _parse_instruction()...")
        instr_token = tok
        parser._advance()  # consume 道
        print(f"  After consume 道: current={parser.current_token}")
        
        # Now in the loop of _parse_instruction
        # First iteration: 新信任路径 (IDENTIFIER)
        if parser.current_token and parser.current_token.type.name == 'IDENTIFIER':
            merged = parser._merge_identifiers()
            print(f"  Merged: type={merged.type.name} value={merged.value!r}")
            print(f"  After merge: current={parser.current_token}")
        
        # Check loop condition
        if parser.current_token:
            ct = parser.current_token
            print(f"  Loop check: current={ct.type.name} in stop_set?")
            # Check if it's in the stop set
            from core.parser import TokenType
            _INST_STOP = (
                TokenType.PERIOD, TokenType.COMMA, TokenType.SEMICOLON,
                TokenType.EOF,
                TokenType.WENYUE, TokenType.DAYUE, TokenType.SHUYUE,
                TokenType.RUO, TokenType.FOUZE,
                TokenType.DAO, TokenType.DE, TokenType.ZIRAN,
                TokenType.WUWEI, TokenType.GU, TokenType.PIN,
                TokenType.ROU, TokenType.PU, TokenType.ZHI, TokenType.ZHIZU,
            )
            in_stop = ct.type in _INST_STOP
            print(f"  In stop: {in_stop}")
            if not in_stop:
                print(f"  ⚠️ NOT in stop! Will consume {ct.type.name}")
        
        # Now call the real _parse_instruction to see what it returns
        # But we already advanced... need fresh parser
        pass
    
    stmt = parser._parse_statement()
    if stmt:
        print(f"  → {stmt.type.name} value={stmt.value!r}")
        if hasattr(stmt, 'operands'):
            for j, op in enumerate(stmt.operands):
                print(f"    op{j}: {op.type.name} value={op.value!r}")
    else:
        print(f"  → None")
    
    loop_count += 1
    if loop_count > 10:
        print("  ⚠️ Too many loops, breaking")
        break

print(f"\n=== Final AST ===")
# Fresh parse for AST
tokens2, _ = tokenize(source)
parser2 = Parser(tokens2, [])
ast = parser2.parse()
for i, stmt in enumerate(ast.statements):
    print(f"  stmt{i}: {stmt.type.name} value={stmt.value!r}")
    if hasattr(stmt, 'operands'):
        for j, op in enumerate(stmt.operands):
            print(f"    op{j}: {op.type.name} value={op.value!r}")
    if hasattr(stmt, 'then_body') and stmt.then_body:
        tb = stmt.then_body
        print(f"    then: {tb.type.name}")
        if hasattr(tb, 'operands'):
            for j, op in enumerate(tb.operands):
                print(f"      op{j}: {op.type.name} value={op.value!r}")
