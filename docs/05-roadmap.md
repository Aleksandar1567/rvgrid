# Roadmap: from one core to a grid

The goal is a small Tenstorrent-style machine: a grid of tiles, each with
simple RISC-V cores and its own SRAM, connected by a network on chip. A host
loads *kernels* into the tiles and launches them.

## What the Tenstorrent model looks like (simplified)

| Tenstorrent (Wormhole / Blackhole) | rvgrid equivalent |
|---|---|
| **Tensix tile**: 5 small RISC-V cores + ~1.5 MB SRAM ("L1") + compute engines + NoC routers | `Tile`: 1 core + 32 KiB L1 for now |
| Two of the cores move data (reader / writer kernels over the NoC); three drive the math engines (unpack / math / pack) | later: a data-mover core + a compute core per tile |
| L1 is shared by the tile's cores and written directly by the NoC | L1 port B is already shared by the core and the `host` port |
| **Circular buffers** in L1 + semaphores sync producer/consumer cores | later: CB pointers in TILECTRL, hardware semaphores |
| **2D torus NoC**, every tile and DRAM bank has an (x, y) address | later: a 2D mesh with XY routing |
| Host (over PCIe) writes kernel binaries into each core's memory, sets runtime args, releases reset | **already how rvgrid boots**: host writes L1, clears `CORE_CTRL.HOLD` |
| tt-metal host API: create program, add kernels per core range, set runtime args, enqueue | later: a Python host runtime driving the testbench |

## Steps

Each step should leave `pytest` green and add its own tests.

### ✅ 0. One tile, one core (this commit)
VexRiscv_Min, dual-port L1, Wishbone decoders and arbiter, timer, UART,
host-loaded boot, determinism test.

### 1. N tiles on a shared bus
- First make L1 fit in 16 block RAMs instead of 32 on ECP5 (see the FPGA
  estimate in the README), otherwise a LFE5U-25F holds only one tile. Root
  cause not pinned down yet. Experiments with the same two ports: 32-bit
  words with byte enables -> 32, 32-bit words without byte enables -> 32,
  four 8-bit lanes -> 32, 16-bit write granularity -> 16. Next: read
  Yosys' `memory_libmap` log, or instantiate DP16KD directly for ECP5.
- `SoC(n_tiles=N)`: the tiles' `ext` ports go through an `Arbiter(N)` into the
  system decoder. Each tile gets a different `TILE_ID`.
- The host addresses one tile at a time: a host-side decoder selects
  `tile[i].host` by an upper address field (`0x8000_0000 + i * 0x0100_0000`).
- Firmware: one binary for all tiles, `tile_id()` picks the work.
- Test: N tiles each sum their slice of an array; host collects the partials.
- Test: determinism still holds with N cores contending for the console.

### 2. Different cores
- More VexRiscv variants: `VexRiscv_Lite` (M extension, small i-cache), or
  your own generated from SpinalHDL. `verilog_sources()` already renames
  modules, so several variants can live in one design.
- `cpu/picorv32.py` (single Verilog file, Wishbone wrapper included) and
  `cpu/serv.py` (bit-serial, tiny). The SoC sees only `ibus`/`dbus`/`hold`/irqs.
- Per-tile `cpu=` and matching `-march` per firmware build.
- This also gives *design diversity*: one core's bug doesn't hit every tile.

### 3. Tiles talk to each other
- Global address = (tile id, local offset). A tile's `ext` can now reach
  another tile's `host` port, so it can write straight into another tile's L1.
- Mailbox / doorbell registers in TILECTRL that drive the receiving core's
  `softwareInterrupt`.
- Hardware semaphores (atomic increment/decrement registers), since
  VexRiscv_Min has no atomics.
- Test: a pipeline of tiles, each transforming a buffer and passing it on.

### 4. Network on chip
- Replace the shared bus with a 2D mesh: one router per tile, XY routing,
  requests and responses as packets (a Wishbone ↔ packet bridge at each tile).
- Measure: latency vs. distance, bandwidth under load, deadlock-freedom tests.
- Diagram: the generated block diagram gains a grid view.

### 5. Data movement without the core
- A DMA engine per tile (or a dedicated data-mover core, like Tenstorrent's
  reader/writer cores): "copy N bytes from tile (x,y) offset A to my L1
  offset B, then bump semaphore S".
- **Circular buffers** in L1: producer/consumer pointers in hardware, so a
  reader kernel and a compute kernel can stream through a small buffer.
- A shared DRAM model (big SRAM or a DRAM controller on a board) as the
  source and destination of data.

### 6. Several cores per tile
- Reader, compute and writer kernels on separate cores sharing L1 (multi-port
  or banked SRAM, an arbiter per bank).
- A compute accelerator for the compute core: a small MAC array, or a
  custom-instruction unit (VexRiscv has a CFU interface).

### 7. Host runtime and kernels
- A Python host API in the spirit of tt-metal:
  `prog = Program(); prog.add_kernel("reader.c", tiles=..., args=...); run(prog)`
- It compiles the kernels, loads them over the host port / NoC, sets runtime
  args in L1, releases the cores, waits, and collects results.
- The same API should drive the simulator and, later, a board over UART/JTAG.

### 8. Hardware
- `python -m rvgrid synth` already reports LUTs, block RAM and Fmax for an
  ECP5-25F: one tile is ~2300 LUTs and closes at ~86 MHz. A ~€30-50 ECP5
  board (Colorlight i5/i9, ULX3S) can hold a few tiles once L1 stops being
  duplicated.
- Needed then: a pin constraint file, a UART bootloader (or JTAG) instead of
  the simulated host port, and the VexRiscv debug variant for GDB.
