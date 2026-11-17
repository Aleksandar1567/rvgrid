"""rvgrid command line.

    python -m rvgrid gen                 Verilog + soc.h + memory.ld into build/
    python -m rvgrid sim hello           build sw/apps/hello and boot it in Verilator
    python -m rvgrid sim hello --waves   ... and write build/sim/verilator-waves/runs/hello/dump.vcd
    python -m rvgrid diagram             regenerate docs/generated/ and the README block
    python -m rvgrid synth               Yosys resource estimate (ECP5 by default)
"""

import argparse
import subprocess
import sys
from pathlib import Path

from .config import SoCConfig
from .gen import BUILD, ROOT, generate_headers, generate_rtl


def build_firmware(app):
    subprocess.run(["make", "-s", "-C", str(ROOT / "sw"), app], check=True)
    return BUILD / "sw" / f"{app}.bin"


def cmd_gen(args):
    cfg = SoCConfig.for_sim() if args.sim else SoCConfig()
    for path in generate_headers(cfg):
        print(path.relative_to(ROOT))
    if not args.headers_only:
        image = Path(args.firmware).read_bytes() if args.firmware else None
        for path in generate_rtl(cfg, firmware=image):
            print(path.relative_to(ROOT))


def cmd_sim(args):
    from .sim.runner import run_firmware, tools_missing

    missing = tools_missing(args.sim)
    if missing:
        sys.exit(f"missing {', '.join(missing)}: run scripts/setup-tools.sh, then `source env.sh`")
    generate_headers(SoCConfig.for_sim())
    image = Path(args.app) if args.app.endswith(".bin") else build_firmware(args.app)
    r = run_firmware(image, sim=args.sim, waves=args.waves, seed=args.seed,
                     max_cycles=args.max_cycles)
    print("----- uart -----")
    print(r["uart"], end="" if r["uart"].endswith("\n") else "\n")
    print("----------------")
    if not r["finished"]:
        print(f"TIMEOUT after {r['cycles']} cycles")
        sys.exit(2)
    print(f"exit code {r['exit_code']}  cycles {r['cycles']}  leds 0x{r['leds']:02x}")
    if args.waves:
        wave = next(Path(r["run_dir"]).glob("*.[fv][sc][td]"), None)   # dump.vcd / .fst
        print(f"waveform: {wave}")
    sys.exit(0 if r["exit_code"] == 0 else 1)


def cmd_diagram(args):
    from .diagram import write_all

    for path in write_all(netlist=not args.no_netlist):
        print(path.relative_to(ROOT))


def cmd_synth(args):
    from .synth import synth

    synth(args.target)


def main(argv=None):
    p = argparse.ArgumentParser(prog="rvgrid", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="generate Verilog, C header and linker map")
    g.add_argument("--headers-only", action="store_true")
    g.add_argument("--firmware", help="bake this .bin into L1 (FPGA build: core boots alone)")
    g.add_argument("--board", dest="sim", action="store_false",
                   help="real UART baud rate instead of the fast simulation divisor")
    g.set_defaults(func=cmd_gen, sim=True)

    s = sub.add_parser("sim", help="run a program on the simulated SoC")
    s.add_argument("app", help="name in sw/apps/ or a path to a .bin")
    s.add_argument("--sim", default="verilator", choices=("verilator", "icarus"))
    s.add_argument("--waves", action="store_true", help="dump an FST/VCD waveform")
    s.add_argument("--seed", type=int, default=1, help="Verilator random-init seed")
    s.add_argument("--max-cycles", type=int, default=2_000_000)
    s.set_defaults(func=cmd_sim)

    d = sub.add_parser("diagram", help="regenerate block diagrams and the memory map")
    d.add_argument("--no-netlist", action="store_true", help="skip the Yosys/netlistsvg schematics")
    d.set_defaults(func=cmd_diagram)

    y = sub.add_parser("synth", help="Yosys synthesis for a resource estimate")
    y.add_argument("--target", default="ecp5", choices=("ecp5", "ice40", "generic"))
    y.set_defaults(func=cmd_synth)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
