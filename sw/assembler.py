#!/usr/bin/env python3
"""Assembler educativo para el Espino Core (subconjunto de RV32E).

Uso:
    python3 assembler.py programa.s programa.hex

El programa hace dos recorridos por el archivo assembly:
1. Calcula la direccion de cada etiqueta.
2. Codifica cada instruccion como una palabra hexadecimal de 32 bits.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


class AssemblyError(ValueError):
    """Error de sintaxis o codificacion asociado a una linea del programa."""


@dataclass(frozen=True)
class SourceInstruction:
    line_number: int
    text: str
    address: int


REGISTER_RE = re.compile(r"x(\d+)$", re.IGNORECASE)
MEMORY_RE = re.compile(r"(.+)\((x\d+)\)$", re.IGNORECASE)


def strip_comment(line: str) -> str:
    """Elimina comentarios iniciados por # o // y espacios exteriores."""
    hash_pos = line.find("#")
    slash_pos = line.find("//")
    positions = [position for position in (hash_pos, slash_pos) if position >= 0]
    if positions:
        line = line[: min(positions)]
    return line.strip()


def parse_register(token: str) -> int:
    match = REGISTER_RE.fullmatch(token.strip())
    if not match:
        raise AssemblyError(f"registro invalido: {token!r}")
    register = int(match.group(1))
    if not 0 <= register <= 15:
        raise AssemblyError(
            f"Espino implementa RV32E: el registro debe estar entre x0 y x15, no x{register}"
        )
    return register


def parse_integer(token: str) -> int:
    try:
        return int(token.strip(), 0)
    except ValueError as error:
        raise AssemblyError(f"numero invalido: {token!r}") from error


def require_signed(value: int, bits: int, name: str) -> int:
    minimum = -(1 << (bits - 1))
    maximum = (1 << (bits - 1)) - 1
    if not minimum <= value <= maximum:
        raise AssemblyError(
            f"{name} fuera de rango: {value}; debe estar entre {minimum} y {maximum}"
        )
    return value & ((1 << bits) - 1)


def require_even_offset(value: int, bits: int, name: str) -> int:
    if value % 2:
        raise AssemblyError(f"{name} debe ser multiplo de 2, no {value}")
    return require_signed(value, bits, name)


def encode_r(opcode: int, funct3: int, funct7: int, rd: int, rs1: int, rs2: int) -> int:
    return (
        (funct7 << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (funct3 << 12)
        | (rd << 7)
        | opcode
    )


def encode_i(opcode: int, funct3: int, rd: int, rs1: int, immediate: int) -> int:
    imm = require_signed(immediate, 12, "inmediato")
    return (imm << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def encode_s(opcode: int, funct3: int, rs1: int, rs2: int, immediate: int) -> int:
    imm = require_signed(immediate, 12, "inmediato")
    imm_low = imm & 0x1F
    imm_high = (imm >> 5) & 0x7F
    return (
        (imm_high << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (funct3 << 12)
        | (imm_low << 7)
        | opcode
    )


def encode_b(opcode: int, funct3: int, rs1: int, rs2: int, offset: int) -> int:
    imm = require_even_offset(offset, 13, "desplazamiento de branch")
    return (
        (((imm >> 12) & 0x1) << 31)
        | (((imm >> 5) & 0x3F) << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (funct3 << 12)
        | (((imm >> 1) & 0xF) << 8)
        | (((imm >> 11) & 0x1) << 7)
        | opcode
    )


def encode_u(opcode: int, rd: int, immediate: int) -> int:
    if not 0 <= immediate <= 0xFFFFF:
        raise AssemblyError(
            f"inmediato U fuera de rango: {immediate}; debe caber en 20 bits"
        )
    return (immediate << 12) | (rd << 7) | opcode


def encode_j(opcode: int, rd: int, offset: int) -> int:
    imm = require_even_offset(offset, 21, "desplazamiento de jal")
    return (
        (((imm >> 20) & 0x1) << 31)
        | (((imm >> 1) & 0x3FF) << 21)
        | (((imm >> 11) & 0x1) << 20)
        | (((imm >> 12) & 0xFF) << 12)
        | (rd << 7)
        | opcode
    )


def split_instruction(text: str) -> tuple[str, list[str]]:
    pieces = text.split(None, 1)
    mnemonic = pieces[0].lower()
    operands = []
    if len(pieces) == 2:
        operands = [operand.strip() for operand in pieces[1].split(",")]
    return mnemonic, operands


def expect_operands(mnemonic: str, operands: list[str], expected: int) -> None:
    if len(operands) != expected:
        raise AssemblyError(
            f"{mnemonic} espera {expected} operandos, pero recibio {len(operands)}"
        )


def parse_memory_operand(token: str) -> tuple[int, int]:
    match = MEMORY_RE.fullmatch(token.replace(" ", ""))
    if not match:
        raise AssemblyError(
            f"operando de memoria invalido: {token!r}; se esperaba inmediato(registro)"
        )
    return parse_integer(match.group(1)), parse_register(match.group(2))


def target_offset(token: str, labels: dict[str, int], address: int) -> int:
    if token in labels:
        return labels[token] - address
    return parse_integer(token)


def encode_instruction(
    instruction: SourceInstruction, labels: dict[str, int]
) -> int:
    mnemonic, operands = split_instruction(instruction.text)

    immediate_ops = {
        "addi": (0b000, 0x13),
        "slti": (0b010, 0x13),
        "sltiu": (0b011, 0x13),
        "xori": (0b100, 0x13),
        "ori": (0b110, 0x13),
        "andi": (0b111, 0x13),
    }
    register_ops = {
        "add": (0b000, 0b0000000),
        "sub": (0b000, 0b0100000),
        "slt": (0b010, 0b0000000),
        "sltu": (0b011, 0b0000000),
        "xor": (0b100, 0b0000000),
        "or": (0b110, 0b0000000),
        "and": (0b111, 0b0000000),
    }
    branches = {
        "beq": 0b000,
        "bne": 0b001,
        "blt": 0b100,
        "bge": 0b101,
        "bltu": 0b110,
        "bgeu": 0b111,
    }

    if mnemonic == "lui":
        expect_operands(mnemonic, operands, 2)
        return encode_u(0x37, parse_register(operands[0]), parse_integer(operands[1]))

    if mnemonic == "auipc":
        expect_operands(mnemonic, operands, 2)
        return encode_u(0x17, parse_register(operands[0]), parse_integer(operands[1]))

    if mnemonic in immediate_ops:
        expect_operands(mnemonic, operands, 3)
        funct3, opcode = immediate_ops[mnemonic]
        return encode_i(
            opcode,
            funct3,
            parse_register(operands[0]),
            parse_register(operands[1]),
            parse_integer(operands[2]),
        )

    if mnemonic in register_ops:
        expect_operands(mnemonic, operands, 3)
        funct3, funct7 = register_ops[mnemonic]
        return encode_r(
            0x33,
            funct3,
            funct7,
            parse_register(operands[0]),
            parse_register(operands[1]),
            parse_register(operands[2]),
        )

    if mnemonic == "lw":
        expect_operands(mnemonic, operands, 2)
        immediate, rs1 = parse_memory_operand(operands[1])
        return encode_i(0x03, 0b010, parse_register(operands[0]), rs1, immediate)

    if mnemonic == "sw":
        expect_operands(mnemonic, operands, 2)
        immediate, rs1 = parse_memory_operand(operands[1])
        return encode_s(0x23, 0b010, rs1, parse_register(operands[0]), immediate)

    if mnemonic in branches:
        expect_operands(mnemonic, operands, 3)
        return encode_b(
            0x63,
            branches[mnemonic],
            parse_register(operands[0]),
            parse_register(operands[1]),
            target_offset(operands[2], labels, instruction.address),
        )

    if mnemonic == "jal":
        expect_operands(mnemonic, operands, 2)
        return encode_j(
            0x6F,
            parse_register(operands[0]),
            target_offset(operands[1], labels, instruction.address),
        )

    if mnemonic == "jalr":
        expect_operands(mnemonic, operands, 2)
        immediate, rs1 = parse_memory_operand(operands[1])
        return encode_i(0x67, 0b000, parse_register(operands[0]), rs1, immediate)

    raise AssemblyError(f"instruccion no soportada: {mnemonic!r}")


def parse_source(source: str) -> tuple[list[SourceInstruction], dict[str, int]]:
    """Primer recorrido: guarda etiquetas y las instrucciones reales."""
    labels: dict[str, int] = {}
    instructions: list[SourceInstruction] = []
    address = 0

    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        line = strip_comment(raw_line)
        if not line or line.startswith("."):
            continue

        while ":" in line:
            label, remainder = line.split(":", 1)
            label = label.strip()
            if not re.fullmatch(r"[A-Za-z_.$][\w.$]*", label):
                raise AssemblyError(f"linea {line_number}: etiqueta invalida: {label!r}")
            if label in labels:
                raise AssemblyError(f"linea {line_number}: etiqueta repetida: {label!r}")
            labels[label] = address
            line = remainder.strip()
            if not line:
                break

        if not line:
            continue
        if line.startswith("."):
            continue

        instructions.append(SourceInstruction(line_number, line, address))
        address += 4

    return instructions, labels


def assemble(source: str) -> list[int]:
    instructions, labels = parse_source(source)
    words: list[int] = []
    for instruction in instructions:
        try:
            words.append(encode_instruction(instruction, labels))
        except AssemblyError as error:
            raise AssemblyError(
                f"linea {instruction.line_number}: {error}\n  {instruction.text}"
            ) from error
    return words


def assemble_file(source_path: Path, output_path: Path) -> None:
    words = assemble(source_path.read_text(encoding="utf-8"))
    output = "".join(f"{word:08x}\n" for word in words)
    output_path.write_text(output, encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte assembly RV32E para Espino Core a un archivo .hex"
    )
    parser.add_argument("source", type=Path, help="archivo de entrada .s")
    parser.add_argument("output", type=Path, help="archivo de salida .hex")
    args = parser.parse_args()

    try:
        assemble_file(args.source, args.output)
    except (AssemblyError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
