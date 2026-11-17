# Firmware build. Every directory in apps/ is one program:
#   apps/<name>/*.c  ->  build/sw/<name>.elf / .bin / .lst / .map
#
#   make            build all programs
#   make hello      build one
#   make CROSS=riscv64-unknown-elf-   use another toolchain prefix

ROOT   := $(abspath ..)
OUT    := $(ROOT)/build/sw
GEN    := $(ROOT)/build/include
PYTHON ?= $(if $(wildcard $(ROOT)/.venv/bin/python),$(ROOT)/.venv/bin/python,python3)

# First toolchain found on PATH (xPack, Debian/Ubuntu, riscv-gnu-toolchain).
CROSS ?= $(firstword $(foreach p,riscv-none-elf- riscv64-unknown-elf- riscv32-unknown-elf-,\
           $(if $(shell command -v $(p)gcc 2>/dev/null),$(p))))
ifeq ($(CROSS),)
  ifneq ($(MAKECMDGOALS),clean)
    $(error No RISC-V GCC on PATH. Run scripts/setup-tools.sh, then `source env.sh`)
  endif
endif
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
OBJDUMP := $(CROSS)objdump
SIZE    := $(CROSS)size

# VexRiscv_Min: RV32I + Zicsr. No M extension, so * and / come from libgcc.
MARCH ?= rv32i_zicsr
MABI  ?= ilp32

CFLAGS := -march=$(MARCH) -mabi=$(MABI) -Os -g -std=gnu11 -Wall -Wextra \
          -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns \
          -ffunction-sections -fdata-sections -Icommon/include -I$(GEN)
LDFLAGS := -nostdlib -nostartfiles -T common/link.ld -L$(GEN) \
           -Wl,--gc-sections -Wl,--no-warn-rwx-segments

COMMON := common/start.S common/lib.c
APPS   := $(notdir $(wildcard apps/*))

.PHONY: all clean $(APPS)
all: $(APPS)

$(APPS): %: $(OUT)/%.bin $(OUT)/%.lst
	@$(SIZE) $(OUT)/$*.elf | tail -1 | awk '{printf "  %-10s text %6d  data %5d  bss %6d\n", "$*", $$1, $$2, $$3}'

# soc.h and memory.ld come from the Python memory map.
$(GEN)/soc.h $(GEN)/memory.ld &: $(wildcard $(ROOT)/rvgrid/*.py $(ROOT)/rvgrid/*/*.py)
	cd $(ROOT) && $(PYTHON) -m rvgrid gen --headers-only

.SECONDARY:          # keep the .elf files (make would delete them as intermediates)
.SECONDEXPANSION:
$(OUT)/%.elf: $(COMMON) common/include/rvgrid.h common/link.ld $(GEN)/soc.h $(GEN)/memory.ld \
              $$(wildcard apps/$$*/*.c apps/$$*/*.h)
	@mkdir -p $(OUT)
	$(CC) $(CFLAGS) $(LDFLAGS) -Wl,-Map=$(OUT)/$*.map -o $@ $(COMMON) $(wildcard apps/$*/*.c) -lgcc

$(OUT)/%.bin: $(OUT)/%.elf
	$(OBJCOPY) -O binary $< $@

$(OUT)/%.lst: $(OUT)/%.elf
	$(OBJDUMP) -d -S --no-show-raw-insn $< > $@

clean:
	rm -rf $(OUT)
