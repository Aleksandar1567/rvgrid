"""Full SoC + VexRiscv + real firmware, in Verilator (via cocotb).

One Verilator build serves all tests: firmware is loaded through the host
port at runtime, not baked into the RTL.
"""

import shutil
import subprocess

import pytest

from rvgrid.gen import BUILD, ROOT
from rvgrid.sim.runner import run_firmware, tools_missing

HAVE_GCC = any(shutil.which(p + "gcc") for p in
               ("riscv-none-elf-", "riscv64-unknown-elf-", "riscv32-unknown-elf-"))

pytestmark = [
    pytest.mark.system,
    pytest.mark.skipif(bool(tools_missing("verilator")) or not HAVE_GCC,
                       reason="needs Verilator + RISC-V GCC: scripts/setup-tools.sh && source env.sh"),
]


@pytest.fixture(scope="session")
def fw():
    subprocess.run(["make", "-s", "-C", str(ROOT / "sw")], check=True)
    return lambda app: BUILD / "sw" / f"{app}.bin"


def check_ok(r):
    assert r["finished"], f"no exit within {r['cycles']} cycles\nuart:\n{r['uart']}"
    assert r["exit_code"] == 0, f"exit code {r['exit_code']}\nuart:\n{r['uart']}"
    assert r["uart_framing_errors"] == 0


def test_hello(fw):
    r = run_firmware(fw("hello"))
    check_ok(r)
    assert "Hello from RISC-V! tile=0\n" in r["uart"]
    assert "fib(12) = 144 in " in r["uart"]
    assert r["leds"] == 0x80


def test_memtest(fw):
    r = run_firmware(fw("memtest"))
    check_ok(r)
    assert "memtest: PASS (0 errors)" in r["uart"]


def test_timer_irq(fw):
    r = run_firmware(fw("timer_irq"))
    check_ok(r)
    assert "timer_irq: 5 ticks" in r["uart"]
    assert r["leds"] == 5


def test_traps(fw):
    r = run_firmware(fw("traps"))
    check_ok(r)
    assert "illegal instruction -> mcause 2\n" in r["uart"]
    assert "ecall               -> mcause 11\n" in r["uart"]
    assert "2 bus errors, first at 0x40000000" in r["uart"]


def test_deterministic_across_random_init(fw):
    """Same program, different random power-up state in every un-reset flop.

    Identical cycle counts, console output and final L1 contents mean the
    design's behaviour depends only on the program, which is the property a
    lockstep many-core system will rely on.
    """
    a = run_firmware(fw("hello"), seed=1, dump_l1=True, name="det-seed1")
    b = run_firmware(fw("hello"), seed=987654, dump_l1=True, name="det-seed2")
    check_ok(a)
    check_ok(b)
    assert a["cycles"] == b["cycles"]
    assert a["uart"] == b["uart"]
    assert a["l1_sha256"] == b["l1_sha256"]


def test_timeout_is_reported(fw):
    r = run_firmware(fw("hello"), max_cycles=500, name="timeout")
    assert not r["finished"]


@pytest.mark.skipif(bool(tools_missing("icarus")), reason="needs Icarus Verilog")
def test_hello_on_icarus(fw):
    """Same RTL on a second, independent simulator."""
    r = run_firmware(fw("hello"), sim="icarus")
    check_ok(r)
    assert "fib(12) = 144" in r["uart"]
