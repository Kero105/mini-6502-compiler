"""
Mini 6502 Compiler
Translates a tiny language of variable assignments into 6502 assembly.

Language:
    a = 5
    b = a + 3
    c = b - a + 10
    # comments start with a hash

Rules:
    - Values are 8-bit (0-255) and wrap around like a real 6502.
    - Operators: + and -
    - A variable must be assigned before it is used.

Usage:
    python compiler.py program.txt            prints 6502 assembly
    python compiler.py program.txt -o out.asm  writes it to a file
"""

import re
import sys

# ---------- 1. Tokenizer ----------

TOKEN_PATTERN = re.compile(r"\s*(?:(\d+)|([A-Za-z_]\w*)|(.))")


def tokenize(line, line_no):
    """Split one line into (kind, value) tokens."""
    tokens = []
    for number, name, symbol in TOKEN_PATTERN.findall(line):
        if number:
            value = int(number)
            if value > 255:
                raise SyntaxError(f"line {line_no}: {value} does not fit in 8 bits (0-255)")
            tokens.append(("NUM", value))
        elif name:
            tokens.append(("NAME", name))
        elif symbol in "=+-":
            tokens.append(("OP", symbol))
        elif symbol.strip():
            raise SyntaxError(f"line {line_no}: unexpected character '{symbol}'")
    return tokens


# ---------- 2. Variable table ----------

class VariableTable:
    """Gives each variable its own byte in zero page ($00-$FF)."""

    def __init__(self):
        self.addresses = {}

    def address_of(self, name, line_no):
        if name not in self.addresses:
            raise NameError(f"line {line_no}: '{name}' is used before it is assigned")
        return self.addresses[name]

    def allocate(self, name):
        if name not in self.addresses:
            if len(self.addresses) >= 256:
                raise MemoryError("out of zero-page memory (256 variables max)")
            self.addresses[name] = len(self.addresses)
        return self.addresses[name]


# ---------- 3. Parser + code generator ----------

def operand(token, variables, line_no):
    """Turn a number or variable into a 6502 operand."""
    kind, value = token
    if kind == "NUM":
        return f"#${value:02X}"          # immediate value, e.g. #$05
    if kind == "NAME":
        return f"${variables.address_of(value, line_no):02X}"  # zero-page address
    raise SyntaxError(f"line {line_no}: expected a number or variable, got '{value}'")


def compile_line(tokens, variables, line_no):
    """Compile `target = term (+|- term)*` into 6502 instructions."""
    if len(tokens) < 3 or tokens[0][0] != "NAME" or tokens[1] != ("OP", "="):
        raise SyntaxError(f"line {line_no}: expected 'name = expression'")

    target = tokens[0][1]
    expr = tokens[2:]
    if len(expr) % 2 == 0:
        raise SyntaxError(f"line {line_no}: expression is incomplete")

    code = [f"; line {line_no}"]
    code.append(f"LDA {operand(expr[0], variables, line_no)}")   # load the first term

    for i in range(1, len(expr), 2):
        op, term = expr[i], expr[i + 1]
        if op == ("OP", "+"):
            code.append("CLC")                                   # clear carry before adding
            code.append(f"ADC {operand(term, variables, line_no)}")
        elif op == ("OP", "-"):
            code.append("SEC")                                   # set carry before subtracting
            code.append(f"SBC {operand(term, variables, line_no)}")
        else:
            raise SyntaxError(f"line {line_no}: expected + or -, got '{op[1]}'")

    # allocate the target last, so `x = x + 1` fails if x was never assigned
    code.append(f"STA ${variables.allocate(target):02X}")       # store the result
    return code


def compile_program(source):
    variables = VariableTable()
    output = []
    for line_no, raw in enumerate(source.splitlines(), start=1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        output.extend(compile_line(tokenize(line, line_no), variables, line_no))
    output.append("BRK")                                         # stop the program
    return output, variables.addresses


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        source = f.read()
    try:
        code, addresses = compile_program(source)
    except (SyntaxError, NameError, MemoryError) as err:
        print(f"Compile error: {err}")
        sys.exit(1)

    asm = "\n".join(code)
    if "-o" in sys.argv:
        with open(sys.argv[sys.argv.index("-o") + 1], "w") as f:
            f.write(asm + "\n")
    else:
        print(asm)

    print("\n; Variable map:", file=sys.stderr)
    for name, addr in addresses.items():
        print(f";   {name} -> ${addr:02X}", file=sys.stderr)


if __name__ == "__main__":
    main()
