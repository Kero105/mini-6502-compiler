"""
Tests for the Mini 6502 Compiler.

Each program is compiled, assembled, and run on an emulated 6502 (py65),
then the variables in memory are checked against the expected values.

Run:
    pip install pytest py65
    pytest test_compiler.py
"""

import pytest
from py65.assembler import Assembler
from py65.devices.mpu6502 import MPU

from compiler import compile_program

START = 0x0600  # same load address Easy6502 uses


def run(source):
    """Compile, assemble, and run a program. Returns {variable: value}."""
    code, addresses = compile_program(source)
    mpu = MPU()
    assembler = Assembler(mpu)

    # pass 1: find where each label lands
    labels, pc = {}, START
    lines = [line for line in code if not line.startswith(";")]
    for line in lines:
        if line.endswith(":"):
            labels[line[:-1]] = pc
        else:
            pc += len(assembler.assemble(_resolve(line, {}, pc), pc))

    # pass 2: assemble with labels resolved into memory
    pc = START
    for line in lines:
        if line.endswith(":"):
            continue
        machine_code = assembler.assemble(_resolve(line, labels, pc), pc)
        assert machine_code is not None, f"could not assemble: {line}"
        for i, byte in enumerate(machine_code):
            mpu.memory[pc + i] = byte
        pc += len(machine_code)

    mpu.pc = START
    for _ in range(100_000):
        if mpu.memory[mpu.pc] == 0x00:  # BRK
            break
        mpu.step()
    return {name: mpu.memory[addr] for name, addr in addresses.items()}


def _resolve(line, labels, pc):
    """Replace a branch label with an absolute address py65 understands."""
    parts = line.split()
    if len(parts) == 2 and parts[0] in ("BEQ", "BNE") and not parts[1].startswith("$"):
        target = labels.get(parts[1], pc + 2)  # placeholder during pass 1
        return f"{parts[0]} ${target:04X}"
    return line


# ---------- Correct results ----------

def test_assign_constant():
    assert run("a = 5") == {"a": 5}


def test_addition_and_subtraction():
    result = run("a = 5\nb = a + 3\nc = b - a + 10\nd = c + c - 1")
    assert result == {"a": 5, "b": 8, "c": 13, "d": 25}


def test_multiply_by_constant():
    assert run("a = 6\nb = a * 7") == {"a": 6, "b": 42}


def test_multiply_two_variables():
    assert run("a = 12\nb = 11\nc = a * b") == {"a": 12, "b": 11, "c": 132}


def test_multiply_before_add():
    # * happens before +, so this is 2 + 12 = 14, not 5 * 4 = 20
    assert run("a = 2 + 3 * 4") == {"a": 14}


def test_multiply_before_subtract():
    assert run("a = 50\nb = a - 4 * 5") == {"a": 50, "b": 30}


def test_chained_multiplication():
    assert run("a = 2 * 3 * 4") == {"a": 24}


def test_multiply_by_zero():
    assert run("a = 9\nb = a * 0\nc = 0 * a") == {"a": 9, "b": 0, "c": 0}


def test_8bit_wraparound():
    # a real 6502 only has 8 bits, so values wrap around
    assert run("x = 3 - 5\ny = 250 + 10\nz = 20 * 20") == {"x": 254, "y": 4, "z": 144}


def test_reassign_variable():
    assert run("a = 1\na = a + 1\na = a * 10") == {"a": 20}


def test_comments_and_blank_lines():
    assert run("# setup\n\na = 4  # four\n\nb = a * a") == {"a": 4, "b": 16}


# ---------- Compile errors ----------

@pytest.mark.parametrize("source, message", [
    ("b = z + 1", "used before it is assigned"),
    ("a = a + 1", "used before it is assigned"),
    ("1 = 2", "expected 'name = expression'"),
    ("a = 300", "does not fit in 8 bits"),
    ("a = 5 +", "incomplete"),
    ("a = 5 * ", "incomplete"),
    ("a = 5 / 2", "unexpected character"),
    ("a = 5 3", "expected +, -, or *"),
])
def test_errors(source, message):
    with pytest.raises((SyntaxError, NameError)) as err:
        compile_program(source)
    assert message in str(err.value)
