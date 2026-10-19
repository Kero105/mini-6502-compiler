"""
Mini 6502 Compiler
Translates a tiny language of variable assignments into 6502 assembly.

Language:
    a = 5
    b = a + 3
    c = b * 2 - a
    # comments start with a hash

Rules:
    - Values are 8-bit (0-255) and wrap around like a real 6502.
    - Operators: +, -, and *  (* is done before + and -)
    - A variable must be assigned before it is used.

Usage:
    python compiler.py program.txt            prints 6502 assembly
    python compiler.py program.txt -o out.asm  writes it to a file
"""

import re
import sys

# Zero-page bytes $FD-$FF are reserved as scratch space for the generated code.
TEMP_SUM = 0xFF      # holds the running total while a product is computed
TEMP_PRODUCT = 0xFE  # holds a finished product before it is added or subtracted
TEMP_MULT = 0xFD     # holds the multiplicand inside a multiply loop
MAX_VARIABLES = 0xFD # so variables live in $00-$FC

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
        elif symbol in "=+-*":
            tokens.append(("OP", symbol))
        elif symbol.strip():
            raise SyntaxError(f"line {line_no}: unexpected character '{symbol}'")
    return tokens


# ---------- 2. Variable table ----------

class VariableTable:
    """Gives each variable its own byte in zero page ($00-$FC)."""

    def __init__(self):
        self.addresses = {}

    def address_of(self, name, line_no):
        if name not in self.addresses:
            raise NameError(f"line {line_no}: '{name}' is used before it is assigned")
        return self.addresses[name]

    def allocate(self, name):
        if name not in self.addresses:
            if len(self.addresses) >= MAX_VARIABLES:
                raise MemoryError(f"out of zero-page memory ({MAX_VARIABLES} variables max)")
            self.addresses[name] = len(self.addresses)
        return self.addresses[name]


# ---------- 3. Parser ----------
# An expression is a list of terms joined by + or -.
# A term is a list of factors joined by *.
# Example: a + b * 3 - c  ->  [('+', [a]), ('+', [b, 3]), ('-', [c])]

def is_factor(token):
    return token[0] in ("NUM", "NAME")


def parse_expression(tokens, line_no):
    if not tokens:
        raise SyntaxError(f"line {line_no}: expression is empty")
    terms = []
    sign = "+"
    i = 0
    while True:
        factors = []
        while True:
            if i >= len(tokens) or not is_factor(tokens[i]):
                raise SyntaxError(f"line {line_no}: expression is incomplete")
            factors.append(tokens[i])
            i += 1
            if i < len(tokens) and tokens[i] == ("OP", "*"):
                i += 1
                continue
            break
        terms.append((sign, factors))
        if i == len(tokens):
            return terms
        if tokens[i] not in (("OP", "+"), ("OP", "-")):
            raise SyntaxError(f"line {line_no}: expected +, -, or *, got '{tokens[i][1]}'")
        sign = tokens[i][1]
        i += 1


# ---------- 4. Code generator ----------

class CodeGenerator:
    def __init__(self):
        self.variables = VariableTable()
        self.label_count = 0

    def operand(self, token, line_no):
        """Turn a number or variable into a 6502 operand."""
        kind, value = token
        if kind == "NUM":
            return f"#${value:02X}"                                  # immediate, e.g. #$05
        return f"${self.variables.address_of(value, line_no):02X}"  # zero-page address

    def multiply(self, factor, line_no):
        """Multiply A by a factor using repeated addition.
        The 6502 has no multiply instruction, so this loop adds the
        multiplicand to itself X times. Result is left in A."""
        self.label_count += 1
        loop = f"mul{self.label_count}"
        done = f"mul{self.label_count}_done"
        return [
            f"STA ${TEMP_MULT:02X}",                 # save the multiplicand
            f"LDX {self.operand(factor, line_no)}",  # X = how many times to add
            "LDA #$00",                              # start the product at 0
            "CPX #$00",
            f"BEQ {done}",                           # anything times 0 is 0
            f"{loop}:",
            "CLC",
            f"ADC ${TEMP_MULT:02X}",                 # product += multiplicand
            "DEX",
            f"BNE {loop}",                           # repeat until X reaches 0
            f"{done}:",
        ]

    def term(self, factors, line_no):
        """Load the first factor into A, then multiply by the rest."""
        code = [f"LDA {self.operand(factors[0], line_no)}"]
        for factor in factors[1:]:
            code.extend(self.multiply(factor, line_no))
        return code

    def assignment(self, tokens, line_no):
        """Compile `target = expression` into 6502 instructions."""
        if len(tokens) < 3 or tokens[0][0] != "NAME" or tokens[1] != ("OP", "="):
            raise SyntaxError(f"line {line_no}: expected 'name = expression'")
        target = tokens[0][1]
        terms = parse_expression(tokens[2:], line_no)

        code = [f"; line {line_no}"]
        sign, factors = terms[0]
        code.extend(self.term(factors, line_no))                     # first term goes into A

        for sign, factors in terms[1:]:
            add = ["CLC", "ADC"] if sign == "+" else ["SEC", "SBC"]  # carry must be set up first
            if len(factors) == 1:
                # simple term: add or subtract it directly
                code.append(add[0])
                code.append(f"{add[1]} {self.operand(factors[0], line_no)}")
            else:
                # product: save the running total, compute the product, then combine
                code.append(f"STA ${TEMP_SUM:02X}")
                code.extend(self.term(factors, line_no))
                code.append(f"STA ${TEMP_PRODUCT:02X}")
                code.append(f"LDA ${TEMP_SUM:02X}")
                code.append(add[0])
                code.append(f"{add[1]} ${TEMP_PRODUCT:02X}")

        # allocate the target last, so `x = x + 1` fails if x was never assigned
        code.append(f"STA ${self.variables.allocate(target):02X}")  # store the result
        return code


def compile_program(source):
    generator = CodeGenerator()
    output = []
    for line_no, raw in enumerate(source.splitlines(), start=1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        output.extend(generator.assignment(tokenize(line, line_no), line_no))
    output.append("BRK")                                             # stop the program
    return output, generator.variables.addresses


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
