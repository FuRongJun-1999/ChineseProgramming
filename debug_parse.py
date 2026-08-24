from core.lexer import tokenize
from core.parser import Parser

source = """道 新信任路径
问曰：如何验证信任？"""

tokens, _ = tokenize(source)
print('Tokens:')
for i, t in enumerate(tokens):
    print(f'  [{i}] {t}')

print()
parser = Parser(tokens, [])
stmt = parser._parse_instruction()
print(f'Instruction result: {stmt}')
print(f'  instruction: {stmt.instruction}')
print(f'  operands: {[(op.type.name, op.value) for op in stmt.operands]}')
print(f'Current token after: {parser.current_token}')
