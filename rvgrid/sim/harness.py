"""cocotb test that boots one firmware image on the full SoC.

It is generic: the runner (rvgrid/sim/runner.py) passes the image and the
knobs through environment variables, and this test writes what it observed
to a JSON file. Assertions live in pytest (tests/system), so the same
harness serves `pytest`, `python -m rvgrid sim <app>` and any future tool.

Boot sequence, the same one a real host would run:
    1. reset the SoC; the core stays held (TILECTRL.CORE_CTRL.HOLD = 1)
    2. write the program into L1 through the host port
    3. clear HOLD; the core starts at L1_BASE
    4. wait for SIMCTRL.EXIT (sim_done) or the cycle budget to run out
"""

import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, First, RisingEdge, Timer
from cocotb.utils import get_sim_time

from .cocotb_bfm import HostPort, UartMonitor

CLK_NS = 10


def env_int(name, default=None):
    v = os.environ.get(name)
    return int(v, 0) if v is not None else default


@cocotb.test()
async def run_firmware(dut):
    image = Path(os.environ["RVGRID_FIRMWARE"]).read_bytes()
    result_path = Path(os.environ["RVGRID_RESULT"])
    max_cycles = env_int("RVGRID_MAX_CYCLES", 2_000_000)
    divisor = env_int("RVGRID_UART_DIVISOR")
    l1_base = env_int("RVGRID_L1_BASE")
    l1_size = env_int("RVGRID_L1_SIZE")
    core_ctrl = env_int("RVGRID_CORE_CTRL")
    dump_l1 = env_int("RVGRID_DUMP_L1", 0)

    Clock(dut.clk, CLK_NS, unit="ns").start()
    host = HostPort(dut)
    dut.rst.value = 1
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0

    await host.load(l1_base, image)
    dut._log.info("loaded %d bytes into L1, releasing core", len(image))

    uart = UartMonitor(dut.uart_tx, dut.clk, divisor,
                       on_line=lambda line: dut._log.info("uart | %s", line))
    cocotb.start_soon(uart.run())

    await host.write(core_ctrl, 0)
    start_ns = get_sim_time("ns")
    done = RisingEdge(dut.sim_done)
    timeout = Timer(max_cycles * CLK_NS, "ns")
    fired = await First(done, timeout)
    cycles = int((get_sim_time("ns") - start_ns) // CLK_NS)
    finished = fired is done

    # Let the last UART frame drain before reading the console.
    await ClockCycles(dut.clk, divisor * 12)
    await host.write(core_ctrl, 1)        # stop the core before peeking at L1

    result = {
        "finished": finished,
        "exit_code": int(dut.sim_code.value) if finished else None,
        "cycles": cycles,
        "uart": uart.text,
        "uart_framing_errors": uart.framing_errors,
        "leds": int(dut.leds.value),
        "image_bytes": len(image),
    }
    if dump_l1:
        mem = await host.dump(l1_base, l1_size)
        result["l1_sha256"] = hashlib.sha256(mem).hexdigest()
    result_path.write_text(json.dumps(result, indent=2))

    if finished:
        dut._log.info("exit code %d after %d cycles", result["exit_code"], cycles)
    else:
        dut._log.warning("no exit after %d cycles (timeout)", max_cycles)
