"""FPGA resource and timing estimate, no board needed.

Synthesises a *board* top-level: the SoC with ``hello`` baked into L1, the
host port tied off, only ``uart_tx`` and ``leds`` as pins. That is the
design you'd load into a real FPGA. Then:

* Yosys ``synth_ecp5`` -> LUT / FF / block-RAM counts
* nextpnr-ecp5 (if installed) -> place & route on a LFE5U-25F and report Fmax

    python -m rvgrid synth                 # ECP5 (e.g. ULX3S, Colorlight i5)
    python -m rvgrid synth --target generic
"""

import json
import shutil
import subprocess

from amaranth import Elaboratable, Module
from amaranth.back import verilog

from .config import SoCConfig
from .gen import BUILD
from .soc import SoC

OUT = BUILD / "synth"


class BoardTop(Elaboratable):
    def __init__(self, cfg, firmware):
        self.soc = SoC(cfg, firmware=firmware)
        self.uart_tx = self.soc.uart_tx
        self.leds = self.soc.leds

    def elaborate(self, platform):
        m = Module()
        m.submodules.soc = self.soc
        # Host port idle: cyc/stb/we stay at their reset value 0.
        return m


def synth(target="ecp5", clk_mhz=50):
    yosys = shutil.which("yosys")
    if not yosys:
        raise SystemExit("yosys not found: run scripts/setup-tools.sh, then `source env.sh`")
    cfg = SoCConfig()
    fw_path = BUILD / "sw" / "hello.bin"
    firmware = fw_path.read_bytes() if fw_path.exists() else bytes(4)
    print(f"firmware in L1: {fw_path if fw_path.exists() else '(none, build sw for a real image)'}")

    OUT.mkdir(parents=True, exist_ok=True)
    top = BoardTop(cfg, firmware)
    sources = top.soc.verilog_sources(OUT)
    (OUT / "board_top.v").write_text(
        verilog.convert(top, name="board_top", ports=[top.uart_tx, top.leds], emit_src=False))
    sources = [OUT / "board_top.v", *sources]

    read = "; ".join(f"read_verilog {s}" for s in sources)
    if target == "ecp5":
        cmd = f"{read}; synth_ecp5 -top board_top -json {OUT / 'board_top.json'}; tee -o {OUT / 'stat.txt'} stat"
    else:
        cmd = f"{read}; synth -top board_top; tee -o {OUT / 'stat.txt'} stat"
    print(f"yosys: synthesising for {target} ...")
    subprocess.run([yosys, "-q", "-l", str(OUT / "yosys.log"), "-p", cmd], check=True)
    print((OUT / "stat.txt").read_text().split("=== design hierarchy ===")[-1].strip())

    nextpnr = shutil.which("nextpnr-ecp5")
    if target != "ecp5" or not nextpnr:
        return
    print(f"\nnextpnr-ecp5: place & route on LFE5U-25F, target {clk_mhz} MHz ...")
    report = OUT / "nextpnr_report.json"
    res = subprocess.run(
        [nextpnr, "--25k", "--package", "CABGA256", "--json", str(OUT / "board_top.json"),
         "--freq", str(clk_mhz), "--report", str(report), "--textcfg", str(OUT / "board_top.config"),
         "--lpf-allow-unconstrained", "--log", str(OUT / "nextpnr.log"), "--quiet"],
    )
    if res.returncode or not report.exists():
        print(f"nextpnr failed, see {OUT / 'nextpnr.log'}")
        return
    rep = json.loads(report.read_text())
    for net, f in rep.get("fmax", {}).items():
        print(f"  Fmax {net}: {f['achieved']:.1f} MHz (target {f['constraint']:.0f} MHz)")
    util = rep.get("utilization", {})
    for cell in ("TRELLIS_COMB", "TRELLIS_FF", "DP16KD", "MULT18X18D", "TRELLIS_IO"):
        if cell in util:
            u = util[cell]
            print(f"  {cell:<13} {u['used']:>6} / {u['available']}")
