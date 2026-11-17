"""Build the SoC simulator once, then run any firmware image on it.

The simulated SoC has no firmware baked in: the testbench loads it through
the host port. So one Verilator build (the slow part, ~tens of seconds)
serves every program and every test.

    from rvgrid.sim.runner import run_firmware
    r = run_firmware("build/sw/hello.bin")
    print(r["uart"], r["exit_code"], r["cycles"])
"""

import json
import os
import shutil
import sys
from pathlib import Path

from ..config import SoCConfig, region
from ..gen import BUILD, ROOT, TOP_NAME, generate_rtl

SIMULATORS = ("verilator", "icarus")

# The cocotb test module (rvgrid.sim.harness) is imported by the Python that
# the simulator embeds. OSS CAD Suite's `vvp` wrapper sets PYTHONHOME to its
# own Python, so that interpreter never reads the venv's .pth files and can't
# see the editable install of rvgrid. cocotb hands sys.path over as
# PYTHONPATH, so putting the repo root on it makes the package importable
# no matter how we were started (`pytest`, `python -m pytest`, `rvgrid sim`).
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

BUILD_ARGS = {
    "verilator": [
        "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-MULTIDRIVEN",
        # Start every flop without a reset value from random garbage, so the
        # determinism test proves the design never depends on it.
        "--x-assign", "unique", "--x-initial", "unique",
    ],
    "icarus": [],
}


def tools_missing(sim="verilator"):
    """Names of required programs that are not on PATH."""
    exe = {"verilator": "verilator", "icarus": "iverilog"}[sim]
    return [t for t in (exe,) if shutil.which(t) is None]


def sim_dir(sim, waves):
    return BUILD / "sim" / (f"{sim}-waves" if waves else sim)


_built = {}


def build(sim="verilator", waves=False, cfg=None):
    from cocotb_tools.runner import get_runner

    cfg = cfg or SoCConfig.for_sim()
    key = (sim, waves, cfg)
    if key in _built:          # once per process; Verilator itself skips no-op rebuilds
        return _built[key]
    sources = generate_rtl(cfg)
    build_args = list(BUILD_ARGS[sim])
    # waves=True makes cocotb add Verilator's --trace (VCD). FST would be
    # smaller, but this Verilator build needs the lz4 headers for it.
    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel=TOP_NAME,
        build_dir=sim_dir(sim, waves),
        build_args=build_args,
        timescale=("1ns", "1ps"),
        waves=waves,
        log_file=sim_dir(sim, waves) / "build.log",
    )
    _built[key] = runner
    return runner


def run_firmware(image_path, sim="verilator", waves=False, seed=1, max_cycles=2_000_000,
                 dump_l1=False, name=None, cfg=None):
    """Boot ``image_path`` (a flat .bin) and return what the testbench saw.

    Keys: finished, exit_code, cycles, uart, leds, [l1_sha256].
    The run directory (logs, waveform) is ``build/sim/<sim>/runs/<name>``.
    """
    from cocotb_tools.runner import get_results

    cfg = cfg or SoCConfig.for_sim()
    image_path = Path(image_path).resolve()
    name = name or image_path.stem
    runner = build(sim, waves, cfg)
    run_dir = sim_dir(sim, waves) / "runs" / name
    run_dir.mkdir(parents=True, exist_ok=True)
    result_file = run_dir / "result.json"
    result_file.unlink(missing_ok=True)

    plusargs = []
    if sim == "verilator":
        plusargs = ["+verilator+rand+reset+2", f"+verilator+seed+{seed}"]
    env = {
        "RVGRID_FIRMWARE": str(image_path),
        "RVGRID_RESULT": str(result_file),
        "RVGRID_MAX_CYCLES": str(max_cycles),
        "RVGRID_UART_DIVISOR": str(cfg.divisor),
        "RVGRID_L1_BASE": str(region(cfg, "L1").base),
        "RVGRID_L1_SIZE": str(region(cfg, "L1").size),
        "RVGRID_CORE_CTRL": str(region(cfg, "TILECTRL").base + 0x08),
        "RVGRID_DUMP_L1": "1" if dump_l1 else "0",
        "COCOTB_LOG_LEVEL": os.environ.get("COCOTB_LOG_LEVEL", "INFO"),
    }
    xml = runner.test(
        test_module="rvgrid.sim.harness",
        hdl_toplevel=TOP_NAME,
        build_dir=sim_dir(sim, waves),
        test_dir=run_dir,
        extra_env=env,
        plusargs=plusargs,
        waves=waves,
        log_file=run_dir / "sim.log",
    )
    _, failed = get_results(xml)
    if failed or not result_file.exists():
        raise RuntimeError(f"simulation failed, see {run_dir / 'sim.log'}")
    result = json.loads(result_file.read_text())
    result["run_dir"] = str(run_dir)
    return result
