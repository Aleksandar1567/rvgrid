# rvgrid: notes for AI agents (and humans)

A custom RISC-V SoC written in Python with Amaranth HDL. VexRiscv is the CPU
(vendored Verilog). Firmware is C. Tests are pytest: Amaranth's simulator for
units, cocotb + Verilator for the full system.

## Commands

```bash
source env.sh                      # venv + ~/tools (RISC-V GCC, OSS CAD Suite) on PATH
pytest tests/unit                  # ~10 s, no external tools; run after any RTL change
pytest                             # + system tests (Verilator, firmware)
python -m rvgrid sim hello         # boot sw/apps/hello, print console + exit code
python -m rvgrid sim hello --waves # + build/sim/verilator-waves/runs/hello/dump.vcd
python -m rvgrid gen               # build/rtl/*.v, build/include/{soc.h,memory.ld}
python -m rvgrid diagram           # docs/generated/, README block, docs/img/*.svg
python -m rvgrid synth             # Yosys + nextpnr estimate for ECP5
make -C sw                         # all firmware -> build/sw/<app>.{elf,bin,lst,map}
```

## Layout

| Path | What |
|---|---|
| `rvgrid/config.py` | **Memory map + SoC parameters. Single source of truth.** |
| `rvgrid/bus/wishbone.py` | `Signature`, `Decoder`, `Arbiter`, `register_slave()` |
| `rvgrid/tile.py`, `rvgrid/soc.py` | Structure: tile = core + L1 + local periphs; SoC = tiles + system bus |
| `rvgrid/periph/*.py` | Peripherals; each declares `REGS` (drives `soc.h` and docs) |
| `rvgrid/cpu/vexriscv.py` | `Instance` wrapper around `vendor/vexriscv/*.v` |
| `rvgrid/sim/` | Amaranth BFM, cocotb BFM (`HostPort`, `UartMonitor`), harness, runner |
| `sw/common/` | `start.S`, `link.ld`, `lib.c`, `include/rvgrid.h` |
| `sw/apps/<name>/` | One program per directory |
| `tests/unit/`, `tests/system/` | pytest |
| `docs/` | Explanations; `docs/generated/` is written by `rvgrid diagram` |

## Invariants (don't break these)

- Every bus is `wishbone.Signature()`: 32-bit data, 30-bit **word** address,
  byte `sel`. Slaves use `register_slave()` so ACK is exactly one cycle and
  comes one cycle after the request.
- Addresses live only in `rvgrid/config.py`. RTL, `soc.h`, `memory.ld`, docs
  and diagrams read them from there. Never hard-code a base address elsewhere
  (firmware uses `soc.h` macros).
- VexRiscv_Min ignores Wishbone ERR. The wrapper turns ERR into ACK, so an
  ERR must never come without the transfer ending.
- `vendor/` is third-party and stays unmodified (module renaming happens at
  build time in `verilog_sources()`).
- `build/`, `docs/generated/` and the README block between
  `<!-- rvgrid:generated:begin/end -->` are generated. Regenerate, don't edit.
- The simulated SoC is host-loaded (no firmware in RTL), so one Verilator
  build serves all programs. Keep it that way.

## Recipes

**New peripheral**
1. `rvgrid/periph/<name>.py`: `wiring.Component` with `bus: In(wishbone.Signature())`,
   a `REGS` tuple, and `register_slave()`.
2. Add a `Region` in `rvgrid/config.py` (`tile_regions` or `system_regions`).
3. Instantiate and connect it in `tile.py` or `soc.py`; add it to the decoder list.
4. Unit test in `tests/unit/`. If software uses it, add an app and a system test.
5. `python -m rvgrid diagram` (the diagram templates in `rvgrid/diagram.py` may
   need the new block).

**New program**: `sw/apps/<name>/main.c` with `int main(void)` (return 0 =
pass), run `python -m rvgrid sim <name>`, add a test in
`tests/system/test_firmware.py`.

**New CPU**: wrapper in `rvgrid/cpu/` exposing `ibus`, `dbus` (Out
`wishbone.Signature()`), `hold`, `timer_irq`, `soft_irq`, `ext_irq` and
`verilog_sources(out_dir)`; select it in `Tile`.

## Gotchas

- Amaranth can't simulate the CPU, so unit tests use `SoC(..., with_cpu=False)`.
- GCC ≥ 12 needs `-march=rv32i_zicsr` for CSR instructions.
- VexRiscv_Min: no `mcycle`, no `mhartid`, no M extension, no misaligned or
  access-fault traps. Use TIMER, TILECTRL.TILE_ID and libgcc.
- cocotb 2.x API (`Clock(..., unit="ns")`, `cocotb_tools.runner`), not 1.x.
