# What a SoC needs besides the CPU

A CPU core on its own does nothing. VexRiscv is a pipeline with two bus ports
(instruction and data), a clock, a reset and a few interrupt pins. Everything
else that makes it a *computer* is the SoC around it, plus a minimum of
software that agrees with that hardware.

Below is the list, in the order you discover you need it. Each item names the
file in this repo that implements it.

## Hardware

### 1. Clock and reset
The core and every peripheral run off one clock (`clk`) with a synchronous
reset (`rst`). Amaranth's `sync` domain gives you both for free.

There's also a second, finer reset: **core hold**. The tile's control block
can keep just the core in reset while memory and the bus are already up, so
something else can write the program into memory first.
→ [`periph/tilectrl.py`](../rvgrid/periph/tilectrl.py), `hold` input of
[`cpu/vexriscv.py`](../rvgrid/cpu/vexriscv.py)

### 2. A bus (interconnect)
The core issues reads and writes to *addresses*. Something has to decide which
block answers each address:

| Piece | Job | Here |
|---|---|---|
| **Protocol** | How a request and its answer look on wires | Wishbone B4 classic (what VexRiscv's ports speak) |
| **Decoder** | Address → which slave | `Decoder` in [`bus/wishbone.py`](../rvgrid/bus/wishbone.py) |
| **Arbiter** | Several masters → one bus | `Arbiter` (core data port + host port) |
| **Error responder** | Answer for addresses nobody owns | built into `Decoder` (ERR) |

Without an error responder, a bad pointer makes the core wait forever for an
answer that never comes. That is the most common way a first SoC "hangs".

**Wishbone or AXI?** Wishbone is a handful of wires and one handshake, which
is ideal for learning and for small cores. AXI has separate read/write
channels, bursts and outstanding transactions; it pays off with caches, DMA
and DRAM. Moving to AXI later only means adding a bridge.

### 3. Memory
The core needs:
- somewhere to fetch its **first instruction**, at the reset vector
  (`externalResetVector` = `L1_BASE` = `0x0000_0000`)
- RAM for data and the stack

Here both are one **dual-port SRAM** ("L1", like the per-core SRAM in a
Tenstorrent Tensix tile). Fetch uses port A and loads/stores use port B, so the
two never wait for each other.
→ [`mem/sram.py`](../rvgrid/mem/sram.py)

### 4. A way to get the program in
Two options, both supported:

| | How | When |
|---|---|---|
| **Baked image** | Firmware is the SRAM's initial contents. The core runs at power-up. | FPGA bitstream, standalone board |
| **Host-loaded** | Core held in reset → host writes L1 through the `host` port → host releases the core | Simulation (one build runs every program); many-core accelerators |

→ `firmware=` argument of `SoC` / `Tile`, and `HostPort.load()` in
[`sim/cocotb_bfm.py`](../rvgrid/sim/cocotb_bfm.py)

### 5. A timer (and interrupts)
VexRiscv_Min has no `mcycle` CSR, so without a timer the software can't even
measure time. The standard RISC-V machine timer (`mtime` / `mtimecmp`) also
drives the core's `timerInterrupt` pin, which gives you periodic interrupts:
the basis of any scheduler.
→ [`periph/timer.py`](../rvgrid/periph/timer.py)

### 6. A console
A UART transmitter, so the program can say what it's doing. In simulation, the
testbench decodes the serial line exactly like a terminal would.
→ [`periph/uart.py`](../rvgrid/periph/uart.py)

### 7. Identity and status
Once there are many tiles running the same binary, each core needs to know
**who it is** (`TILECTRL.TILE_ID`). Something also has to notice failures the
core can't: VexRiscv_Min ignores bus errors, so the tile counts them and keeps
the first faulting address.
→ [`periph/tilectrl.py`](../rvgrid/periph/tilectrl.py)

### 8. Simulation control
A register the program writes to end the simulation with an exit code. Without
it, every testbench needs a guess of "how long is long enough". On an FPGA the
register is harmless.
→ [`periph/simctrl.py`](../rvgrid/periph/simctrl.py)

### 9. Pins
Whatever leaves the chip: `uart_tx`, `leds[7:0]`, the host port, and the
sim-only `sim_done`/`sim_code`.

## Software (the other half of the contract)

| Piece | Why | Here |
|---|---|---|
| **Cross compiler** | Build RV32I code on an x86 PC | xPack `riscv-none-elf-gcc`, `-march=rv32i_zicsr -mabi=ilp32` |
| **Startup code** | Set `sp`/`gp`, zero `.bss`, set `mtvec`, call `main` | [`sw/common/start.S`](../sw/common/start.S) |
| **Linker script** | Where code, data and stack go in the address map | [`sw/common/link.ld`](../sw/common/link.ld) + generated `memory.ld` |
| **Register header** | Peripheral addresses as C macros | generated `build/include/soc.h` |
| **Trap handler** | What happens on an exception or interrupt | `trap_entry` in `start.S`, `trap_handler()` in `lib.c` |
| **Tiny libc** | `printf`, `memset`, `memcpy`. No real libc is linked. | [`sw/common/lib.c`](../sw/common/lib.c) |
| **libgcc** | `*`, `/` and `%` on a core without the M extension | linked with `-lgcc` |

## The glue: one memory map

The decoders in the RTL, `soc.h`, `memory.ld`, the docs and the diagrams are
all **generated from one table**, [`rvgrid/config.py`](../rvgrid/config.py).
Moving a peripheral is a one-line change, and the hardware and the software
can't disagree about where it is.

## Not needed yet, needed later

| Block | When |
|---|---|
| Debug module (JTAG, VexRiscv `DebugPlugin`) | Stepping through code on a real board |
| Interrupt controller (PLIC/CLIC) | More than a couple of interrupt sources |
| DMA engine | Moving data without the core: the heart of the Tenstorrent model |
| DRAM controller | Data larger than on-chip SRAM |
| Atomics / hardware semaphores / mailboxes | Several cores sharing data |
| Network on chip | More tiles than one shared bus can serve |

See [05-roadmap.md](05-roadmap.md) for the order these come in.
