# Simulation and tests

Two layers, both driven by `pytest`, both pure Python on the test side.

| Layer | What runs | Simulator | Speed | Needs |
|---|---|---|---|---|
| **Unit** (`tests/unit`) | One block, or the whole SoC *without* the CPU | Amaranth's built-in Python simulator | ~10 s total | only `pip install` |
| **System** (`tests/system`) | Full SoC + VexRiscv + real C firmware | Verilator (or Icarus) via cocotb | ~40 s first time (Verilator build), then seconds per program | `scripts/setup-tools.sh` |

```
pytest tests/unit          # fast loop while editing RTL
pytest                     # everything
pytest -k memtest -s       # one system test, with live console output
```

## Unit tests: Amaranth simulator

Amaranth can't simulate the VexRiscv Verilog, so these tests drive the
buses directly with a small Wishbone master (`rvgrid/sim/amaranth_bfm.py`):

```python
async def tb(ctx):
    r = await wb_write(ctx, dut.host, 0x1000_1000, 0xA5)   # LEDS
    assert ctx.get(dut.leds) == 0xA5
```

`test_soc_fabric.py` builds the real `SoC` with `with_cpu=False` and uses the
host port where the core would be. That covers both decoders, the arbiter, L1,
the tile → system path and the bus-error capture, with no external tools.

To look at a unit test's waveform, pass `vcd="x.vcd"` to `run()`.

## System tests: cocotb + Verilator

```
rvgrid/sim/runner.py    build the simulator once; run_firmware(bin) → dict
rvgrid/sim/harness.py   the cocotb test: reset, load, release, wait, report
rvgrid/sim/cocotb_bfm.py  HostPort (Wishbone master) + UartMonitor (serial decoder)
```

The simulated SoC has **no firmware baked in**. The harness boots it like a
host would (see the sequence diagram in [02-architecture.md](02-architecture.md)):
reset → write the `.bin` into L1 through `host__*` → clear `CORE_CTRL.HOLD` →
wait for `sim_done` → hold the core again. So one Verilator build runs every
program, and switching programs costs no rebuild.

The harness only observes and writes `result.json`:

```json
{ "finished": true, "exit_code": 0, "cycles": 27685,
  "uart": "Hello from RISC-V! tile=0\n...", "leds": 128, "l1_sha256": "..." }
```

`pytest` makes the assertions. `python -m rvgrid sim <app>` prints the same
result for a human.

### Determinism test
Verilator is built with `--x-assign unique --x-initial unique` and run with
`+verilator+rand+reset+2 +verilator+seed+N`, so every flop without a reset
value starts as random garbage that changes with the seed. The test runs
`hello` with two seeds and requires bit-identical cycle count, console output
and L1 contents (read back over the host port after the run).

## Waveforms

```
python -m rvgrid sim hello --waves
# → build/sim/verilator-waves/runs/hello/dump.vcd  (~70 MB for hello)
gtkwave build/sim/verilator-waves/runs/hello/dump.vcd docs/hello.gtkw
```

`docs/hello.gtkw` opens with the interesting signals already added:
the host port, the core's ibus/dbus, the arbiter grant, the timer interrupt,
the UART line and `sim_done`. [Surfer](https://surfer-project.org) (in OSS
CAD Suite, and as a VS Code extension) opens the same file.

The output is VCD rather than FST because this Verilator build needs the lz4
headers for FST (`sudo apt install liblz4-dev`).

`python -m rvgrid diagram` also turns two windows of this VCD into the SVG
timing diagrams in `docs/img/wave_*.svg` (`rvgrid/wave.py`, no dependencies).

The waves build is a separate Verilator build (`build/sim/verilator-waves`),
so turning tracing on or off never forces the other one to rebuild.

## Where to look when something fails

| Symptom | Look at |
|---|---|
| assertion on `uart` / `exit_code` | the test output shows the console; `build/sim/verilator/runs/<name>/sim.log` |
| `TIMEOUT` | the program never wrote EXIT. Run `--waves`, find the last `ibus__adr`, look it up in `build/sw/<app>.lst` |
| exit code `0x1xx` | an exception: `0x100 + mcause`, details printed on the console |
| Verilator build errors | `build/sim/verilator/build.log` |
