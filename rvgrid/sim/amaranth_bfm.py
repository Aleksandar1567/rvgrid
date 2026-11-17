"""Wishbone master for Amaranth's built-in Python simulator.

Used by the unit tests (tests/unit). Usage inside an async testbench::

    async def tb(ctx):
        r = await wb_write(ctx, dut.bus, 0x1000_0000, 0x41)
        assert r.ack
        r = await wb_read(ctx, dut.bus, 0x1000_0004)
        print(hex(r.data))
"""

from dataclasses import dataclass


@dataclass
class Result:
    ack: bool
    err: bool
    data: int
    cycles: int


async def _transfer(ctx, bus, byte_addr, we, data=0, sel=0xF, timeout=32):
    ctx.set(bus.adr, byte_addr >> 2)
    ctx.set(bus.dat_w, data)
    ctx.set(bus.sel, sel)
    ctx.set(bus.we, we)
    ctx.set(bus.cyc, 1)
    ctx.set(bus.stb, 1)
    for cycles in range(1, timeout + 1):
        await ctx.tick()
        ack, err = ctx.get(bus.ack), ctx.get(bus.err)
        if ack or err:
            result = Result(bool(ack), bool(err), ctx.get(bus.dat_r), cycles)
            break
    else:
        result = Result(False, False, 0, timeout)
    # The transfer ends at the clock edge that samples ACK.
    ctx.set(bus.cyc, 0)
    ctx.set(bus.stb, 0)
    ctx.set(bus.we, 0)
    await ctx.tick()
    return result


async def wb_write(ctx, bus, byte_addr, data, sel=0xF, timeout=32):
    return await _transfer(ctx, bus, byte_addr, 1, data, sel, timeout)


async def wb_read(ctx, bus, byte_addr, timeout=32):
    return await _transfer(ctx, bus, byte_addr, 0, timeout=timeout)


def run(dut, testbench, vcd=None, background=()):
    """Simulate ``dut`` with one clock and run ``testbench(ctx)`` to completion."""
    from amaranth.sim import Simulator

    sim = Simulator(dut)
    sim.add_clock(1e-8)
    for proc in background:
        sim.add_process(proc)
    sim.add_testbench(testbench)
    if vcd:
        with sim.write_vcd(vcd):
            sim.run()
    else:
        sim.run()
