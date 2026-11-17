# Software

## Toolchain

`scripts/setup-tools.sh` installs xPack `riscv-none-elf-gcc` into `~/tools`.
`source env.sh` puts it on PATH. The Makefile also accepts
`riscv64-unknown-elf-` (Ubuntu's `gcc-riscv64-unknown-elf`) or any prefix via
`make CROSS=...`.

Flags that matter (`sw/Makefile`):

| Flag | Why |
|---|---|
| `-march=rv32i_zicsr -mabi=ilp32` | What VexRiscv_Min implements. Since GCC 12, `csrr`/`csrw` need `_zicsr` spelled out. |
| `-ffreestanding -nostdlib -nostartfiles` | No OS and no libc; we bring our own startup code. |
| `-lgcc` | No M extension, so `a * b` and `a / b` become calls to `__mulsi3`, `__udivsi3`, … |
| `-fno-tree-loop-distribute-patterns` | Otherwise GCC turns the loop inside our `memset` into a call to `memset`. |
| `-ffunction-sections -fdata-sections -Wl,--gc-sections` | Drop unused code; L1 is only 32 KiB. |

## Layout of a program in memory

```
0x0000_0000  ┌──────────────────┐  ← reset vector, _start (start.S)
             │ .text            │
             │ .rodata          │
             │ .data / .sdata   │  ← the .bin file ends here
             │ .bss / .sbss     │  zeroed by start.S
             │   free           │
             │ stack ↓          │  4 KiB reserved (ASSERT in link.ld)
0x0000_8000  └──────────────────┘  ← __stack_top
```

The `.bin` image is copied to `L1_BASE` unchanged, by the host or baked into
the SRAM. `.data` is therefore already in place and needs no copy loop.

`memory.ld` (the `MEMORY` block) and `soc.h` are **generated** from
`rvgrid/config.py` by `python -m rvgrid gen`; `sw/Makefile` regenerates them
when the Python changes. Don't edit them by hand.

## What happens before `main()`

`sw/common/start.S`:
1. zero `x1`..`x31`. The register file has no reset; without this, its random
   power-up contents end up on the stack (harmless, but two runs or two
   lockstep cores would then differ in memory).
2. `gp` ← `__global_pointer$`, with relaxation off for this one instruction.
   Otherwise the linker would "optimise" it into a `gp`-relative load of
   itself.
3. `sp` ← top of L1
4. zero `.bss`
5. `mtvec` ← `trap_entry`
6. `call main`, then `sim_exit(return value)`

## Traps

`trap_entry` (in `start.S`) saves the 16 caller-saved registers, calls

```c
uint32_t trap_handler(uint32_t mcause, uint32_t mepc, uint32_t mtval);
```

and resumes at the address it returns. The default handler (weak, in `lib.c`)
passes interrupts to `irq_handler(cause)` and ends the simulation on any
exception with exit code `0x100 + mcause`, after printing the cause. Programs
override either function:

- `timer_irq` overrides `irq_handler` to count timer ticks
- `traps` overrides `trap_handler` to skip faulting instructions

## Board support API (`sw/common/include/rvgrid.h`)

| | |
|---|---|
| `printf(fmt, ...)` | `%c %s %d %u %x %p %%`, zero-pad width (`%08x`) |
| `uart_putc`, `uart_puts` | console |
| `timer_now()` | 64-bit cycle count |
| `timer_set_cmp(t)` | timer interrupt at cycle `t` |
| `tile_id()` | which tile this is |
| `sim_exit(code)` | end the simulation (0 = pass) |
| `csr_read/write/set/clear(name)` | CSR access, e.g. `csr_set(mie, MIE_MTIE)` |
| `UART_TXDATA`, `LEDS_OUT`, … | every register, from `soc.h` |

## Adding a program

```
mkdir sw/apps/blink
$EDITOR sw/apps/blink/main.c      # int main(void) { ... return 0; }
python -m rvgrid sim blink         # builds it and boots it
```

Any `*.c` in the directory is compiled. Outputs go to `build/sw/`:
`blink.elf` (with debug info), `blink.bin` (what gets loaded), `blink.lst`
(disassembly interleaved with source), `blink.map` (where every symbol went).
To have it checked by `pytest`, add a test to `tests/system/test_firmware.py`.
