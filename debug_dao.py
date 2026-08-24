from core.lexer import tokenize
from core.parser import Parser, TokenType

source = """道 新信任路径
问曰：如何验证信任？"""

tokens, _ = tokenize(source)
print("=== Tokens ===")
for i, t in enumerate(tokens):
    print(f"  [{i}] {t}")

print()
parser = Parser(tokens, [])

# 直接调用 _parse_instruction
print("=== Before _parse_instruction ===")
print(f"  current: {parser.current_token}")

stmt = parser._parse_instruction()

print(f"\n=== After _parse_instruction ===")
print(f"  returned: {stmt}")
print(f"  type: {stmt.type.name}")
print(f"  instruction: {stmt.instruction}")
print(f"  operands: {[(op.type.name, op.value) for op in stmt.operands]}")
print(f"  current: {parser.current_token}")
