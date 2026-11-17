"""Eight output pins. On a board they drive LEDs; in simulation they show
firmware progress without any software stack at all."""

from amaranth import Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ..bus import wishbone
from ..bus.wishbone import register_slave
from .base import Reg


class LEDs(wiring.Component):
    REGS = (
        Reg("OUT", 0x0, "rw", "Pin state, bits 7..0"),
    )

    bus: In(wishbone.Signature())
    pins: Out(8)

    def elaborate(self, platform):
        m = Module()
        access = register_slave(m, self.bus)
        with m.If(access & self.bus.we):
            m.d.sync += self.pins.eq(self.bus.dat_w[:8])
        with m.If(access & ~self.bus.we):
            m.d.sync += self.bus.dat_r.eq(self.pins)
        return m
