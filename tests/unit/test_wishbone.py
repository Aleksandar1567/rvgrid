"""Decoder and arbiter, tested in Amaranth's Python simulator (no tools needed)."""

from amaranth import Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, connect, flipped

from rvgrid.bus import wishbone
from rvgrid.bus.wishbone import Arbiter, Decoder, register_slave
from rvgrid.sim.amaranth_bfm import run, wb_read, wb_write


class TagSlave(wiring.Component):
    """Answers reads with ``tag << 24 | word offset`` and remembers the last write."""
    bus: In(wishbone.Signature())
    last_write: Out(32)

    def __init__(self, tag):
        self.tag = tag
        super().__init__()

    def elaborate(self, platform):
        m = Module()
        access = register_slave(m, self.bus)
        with m.If(access & self.bus.we):
            m.d.sync += self.last_write.eq(self.bus.dat_w)
        with m.If(access & ~self.bus.we):
            m.d.sync += self.bus.dat_r.eq((self.tag << 24) | self.bus.adr[:10])
        return m


class DecoderBench(wiring.Component):
    bus: In(wishbone.Signature())

    def elaborate(self, platform):
        m = Module()
        m.submodules.dec = dec = Decoder([("a", 0x0000_0000, 0x1000), ("b", 0x8000_0000, 0x1000)])
        m.submodules.a = self.a = TagSlave(0xA)
        m.submodules.b = self.b = TagSlave(0xB)
        connect(m, flipped(self.bus), dec.bus)
        connect(m, dec.a, self.a.bus)
        connect(m, dec.b, self.b.bus)
        return m


def test_decoder_routes_by_address():
    dut = DecoderBench()

    async def tb(ctx):
        r = await wb_read(ctx, dut.bus, 0x0000_0010)
        assert r.ack and not r.err and r.data == 0x0A00_0004
        r = await wb_read(ctx, dut.bus, 0x8000_0FFC)
        assert r.ack and r.data == 0x0B00_03FF
        r = await wb_write(ctx, dut.bus, 0x8000_0000, 0x1234_5678)
        assert r.ack and r.cycles == 1
        await ctx.tick()
        assert ctx.get(dut.b.last_write) == 0x1234_5678
        assert ctx.get(dut.a.last_write) == 0

    run(dut, tb)


def test_decoder_unmapped_gives_one_err():
    dut = DecoderBench()

    async def tb(ctx):
        r = await wb_read(ctx, dut.bus, 0x4000_0000)
        assert r.err and not r.ack
        # ERR is a single-cycle pulse, then the bus is idle again.
        await ctx.tick()
        assert not ctx.get(dut.bus.err)
        r = await wb_read(ctx, dut.bus, 0x0000_0000)
        assert r.ack and r.data == 0x0A00_0000

    run(dut, tb)


class ArbiterBench(wiring.Component):
    m0: In(wishbone.Signature())
    m1: In(wishbone.Signature())

    def elaborate(self, platform):
        m = Module()
        m.submodules.arb = arb = Arbiter(2)
        m.submodules.slave = self.slave = TagSlave(0x5)
        connect(m, flipped(self.m0), arb.m0)
        connect(m, flipped(self.m1), arb.m1)
        connect(m, arb.bus, self.slave.bus)
        return m


def test_arbiter_alternates_between_busy_masters():
    """Both masters keep requesting; the arbiter must interleave them."""
    dut = ArbiterBench()
    order = []

    async def tb(ctx):
        for mi in (dut.m0, dut.m1):
            ctx.set(mi.cyc, 1)
            ctx.set(mi.stb, 1)
        for _ in range(16):
            await ctx.tick()
            for name, mi in (("m0", dut.m0), ("m1", dut.m1)):
                if ctx.get(mi.ack):
                    order.append(name)
        assert ctx.get(dut.m0.ack) + ctx.get(dut.m1.ack) <= 1

    run(dut, tb)
    assert len(order) >= 4
    assert all(a != b for a, b in zip(order, order[1:], strict=False)), order


def test_arbiter_single_master_full_speed():
    dut = ArbiterBench()

    async def tb(ctx):
        for addr in range(0, 32, 4):
            r = await wb_read(ctx, dut.m1, addr)
            assert r.ack and r.data == 0x0500_0000 | (addr >> 2)

    run(dut, tb)
