"""Dual-port on-chip SRAM: the tile's "L1".

Port A (``ibus``) is read-only and feeds instruction fetch. Port B (``dbus``)
is read/write with byte enables and serves loads, stores and the host loader.
Two ports mean fetch and data access never wait for each other, so instruction
timing does not depend on what the data side is doing. That keeps the core's
cycle count deterministic, which matters once several tiles run in lockstep.

On an FPGA this maps 1:1 to block RAM (one read port + one read/write port).
"""

from amaranth import Module
from amaranth.lib import wiring
from amaranth.lib.memory import Memory
from amaranth.lib.wiring import In

from ..bus import wishbone
from ..bus.wishbone import register_slave


class SRAM(wiring.Component):
    ibus: In(wishbone.Signature())
    dbus: In(wishbone.Signature())

    def __init__(self, size, init=()):
        if size % 4 or size & (size - 1):
            raise ValueError("SRAM size must be a power of two")
        self.size = size
        self.depth = size // 4
        init = list(init)
        if len(init) > self.depth:
            raise ValueError(f"init image is {len(init) * 4} B, SRAM is {size} B")
        self.mem = Memory(shape=32, depth=self.depth, init=init)
        super().__init__()

    def elaborate(self, platform):
        m = Module()
        m.submodules.mem = mem = self.mem
        aw = self.depth.bit_length() - 1

        # Port A: instruction fetch, read-only (a write here is acked and dropped;
        # the core never writes through its fetch port).
        rd_a = mem.read_port()
        m.d.comb += rd_a.addr.eq(self.ibus.adr[:aw])
        register_slave(m, self.ibus)
        m.d.comb += self.ibus.dat_r.eq(rd_a.data)

        # Port B: data. SEL picks which bytes a store updates.
        rd_b = mem.read_port()
        wr_b = mem.write_port(granularity=8)
        access_b = register_slave(m, self.dbus)
        m.d.comb += [
            rd_b.addr.eq(self.dbus.adr[:aw]),
            wr_b.addr.eq(self.dbus.adr[:aw]),
            wr_b.data.eq(self.dbus.dat_w),
            self.dbus.dat_r.eq(rd_b.data),
        ]
        with m.If(access_b & self.dbus.we):
            m.d.comb += wr_b.en.eq(self.dbus.sel)
        return m
