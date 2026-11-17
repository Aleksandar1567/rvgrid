"""Machine timer (RISC-V ``mtime`` / ``mtimecmp``), one per tile.

``mtime`` counts clock cycles from reset. The interrupt line (wired to the
core's ``timerInterrupt``) is high while ``mtime >= mtimecmp``, which is the
standard RISC-V machine-timer contract: the handler acknowledges by moving
``mtimecmp`` forward.

VexRiscv_Min has no ``mcycle``/``rdcycle`` CSRs, so this is also the only way
firmware can measure time. Read 64-bit values hi-lo-hi to avoid a carry race.
"""

from amaranth import Module, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ..bus import wishbone
from ..bus.wishbone import register_slave
from .base import Reg


class Timer(wiring.Component):
    REGS = (
        Reg("MTIME_LO", 0x0, "ro", "Cycle counter, low word"),
        Reg("MTIME_HI", 0x4, "ro", "Cycle counter, high word"),
        Reg("MTIMECMP_LO", 0x8, "rw", "Compare value, low word", reset=0xFFFFFFFF),
        Reg("MTIMECMP_HI", 0xC, "rw", "Compare value, high word", reset=0xFFFFFFFF),
    )

    bus: In(wishbone.Signature())
    irq: Out(1)

    def elaborate(self, platform):
        m = Module()
        bus = self.bus

        mtime = Signal(64)
        mtimecmp = Signal(64, init=2**64 - 1)
        m.d.sync += mtime.eq(mtime + 1)
        m.d.comb += self.irq.eq(mtime >= mtimecmp)

        access = register_slave(m, bus)
        idx = bus.adr[:2]
        with m.If(access & bus.we):
            with m.Switch(idx):
                with m.Case(2):
                    m.d.sync += mtimecmp[:32].eq(bus.dat_w)
                with m.Case(3):
                    m.d.sync += mtimecmp[32:].eq(bus.dat_w)
        with m.If(access & ~bus.we):
            with m.Switch(idx):
                with m.Case(0):
                    m.d.sync += bus.dat_r.eq(mtime[:32])
                with m.Case(1):
                    m.d.sync += bus.dat_r.eq(mtime[32:])
                with m.Case(2):
                    m.d.sync += bus.dat_r.eq(mtimecmp[:32])
                with m.Case(3):
                    m.d.sync += bus.dat_r.eq(mtimecmp[32:])
        return m
