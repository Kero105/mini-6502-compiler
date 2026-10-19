# Mini 6502 Compiler

A small compiler, written in Python, that translates a simple language of variable assignments into 6502 assembly.

## Example

Input (`example.txt`):

```
a = 5
b = a + 3
c = b - a + 10
d = c + c - 1
```

Output:

```
LDA #$05
STA $00
LDA $00
CLC
ADC #$03
STA $01
...
BRK
```

When you run it on a 6502, memory ends up as `$00 = 05`, `$01 = 08`, `$02 = 0D` and `$03 = 19` (5, 8, 13 and 25).

## How it works

1. **Tokenizer:** splits each line into numbers, names and operators.
2. **Variable table:** gives each variable one byte in zero page (`$00`, `$01`, ...).
3. **Code generator:** loads the first term into the accumulator (`LDA`), adds (`CLC` + `ADC`) or subtracts (`SEC` + `SBC`) each following term, and stores the result (`STA`).

Values are 8-bit and wrap around the same way they do on real hardware (for example, `3 - 5 = 254`). The compiler reports errors for undefined variables, numbers over 255 and malformed lines.

## Run it

```
python compiler.py example.txt
```

To test the output, paste it into [Easy6502](https://skilldrick.github.io/easy6502/), click **Assemble** and then **Run**, and check the memory monitor at `$0000`.

## Next steps

Add multiplication, comparisons and `if` statements, loops, and output to the screen.
