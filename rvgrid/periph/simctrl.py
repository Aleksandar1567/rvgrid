"""Simulation control: lets firmware end the testbench with an exit code.

Writing EXIT raises ``done`` and puts the value on ``code`` (0 = pass). The
testbench watches those two top-level pins. On a real FPGA nothing listens and
the block is harmless (a few flip-flops), so the same RTL runs everywhere.
"""

from amaranth import Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ..bus import wishbone
from ..bus.wishbone import register_slave
from .base import Reg


class SimCtrl(wiring.Component):
    REGS = (
        Reg("EXIT", 0x0, "wo", "Write the exit code (0 = pass) to stop the simulation"),
    )

    bus: In(wishbone.Signature())
    done: Out(1)
    code: Out(32)

    def elaborate(self, platform):
        m = Module()
        access = register_slave(m, self.bus)
        with m.If(access & self.bus.we & ~self.done):
            m.d.sync += [self.done.eq(1), self.code.eq(self.bus.dat_w)]
        return m
