# Copyright 2026 Universidad de los Andes.
# Licensed under the Solderpad Hardware License, Version 0.51 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: SHL-0.51
#
# Course: Arquitectura de Computadores (2026)
#
# Authors:
# - Nicolás Villegas <navillegas@miuandes.cl>

# Assembles the .s sources in this folder into the $readmemh-style .hex
# files consumed by the pochoco_soc RTL.

# Change if needed
PREFIX  ?= riscv64-unknown-elf-
AS      = $(PREFIX)as
LD      = $(PREFIX)ld
OBJCOPY = $(PREFIX)objcopy

ASFLAGS = -march=rv32e -mabi=ilp32e
LDFLAGS = -m elf32lriscv -Ttext=0x0 --no-relax

SRCS  = $(wildcard *.s)
HEXS  = $(SRCS:.s=.hex)
PROGS = $(basename $(SRCS))

# El proyecto final debe usar el assembler desarrollado por el grupo.
# Esta regla especifica que game.hex se genera con assembler.py.
game.hex: game.s assembler.py
	python3 assembler.py game.s game.hex

all: $(HEXS)

.PHONY: $(PROGS)
$(PROGS): %: %.hex

%.hex: %.s
	$(AS) $(ASFLAGS) -o $*.o $<
	$(LD) $(LDFLAGS) -o $*.elf $*.o
	$(OBJCOPY) -O binary $*.elf $*.bin
	od -An -tx4 -v $*.bin | tr -s ' ' '\n' | sed '/^$$/d' > $@
	rm -f $*.o $*.elf $*.bin

clean:
	rm -f *.o *.elf *.bin

test: game.hex
	python3 -m unittest -v test_assembler.py

.PHONY: all clean test
