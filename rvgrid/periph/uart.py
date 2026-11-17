"""UART transmitter (8N1): the SoC's console.

Frame on the ``tx`` line, LSB first, ``divisor`` clock cycles per bit:

    idle ‾‾‾\\_start_/ d0 / d1 / ... / d7 /‾stop‾‾‾ idle

Software polls STATUS.TX_BUSY, then writes the byte to TXDATA.
In simulation the divisor is set very low (a few cycles per bit) so printing
doesn't dominate runtime; on a board it is clk_hz / baud.
"""

from amaranth import Cat, Const, Module, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ..bus import wishbone
from ..bus.wishbone import register_slave
from .base import Reg


class UART(wiring.Component):
    REGS = (
        Reg("TXDATA", 0x0, "wo", "Write a byte to send it (dropped while TX_BUSY)"),
        Reg("STATUS", 0x4, "ro", "bit0 TX_BUSY: a frame is being shifted out"),
        Reg("DIVISOR", 0x8, "rw", "Clock cycles per bit (16 bits)"),
    )

    bus: In(wishbone.Signature())
    tx: Out(1, init=1)

    def __init__(self, divisor):
        if not 2 <= divisor < 2**16:
            raise ValueError("UART divisor must be 2..65535")
        self.default_divisor = divisor
        super().__init__()

    def elaborate(self, platform):
        m = Module()
        bus = self.bus

        divisor = Signal(16, init=self.default_divisor)
        shreg = Signal(10, init=0x3FF)     # stop, d7..d0, start (LSB goes first)
        bits_left = Signal(range(11))
        tick = Signal(16)
        busy = Signal()
        m.d.comb += [busy.eq(bits_left != 0), self.tx.eq(shreg[0])]

        # Bit timing.
        with m.If(busy):
            with m.If(tick == 0):
                m.d.sync += [
                    tick.eq(divisor - 1),
                    shreg.eq(Cat(shreg[1:], Const(1, 1))),
                    bits_left.eq(bits_left - 1),
                ]
            with m.Else():
                m.d.sync += tick.eq(tick - 1)

        # Registers.
        access = register_slave(m, bus)
        idx = bus.adr[:2]
        with m.If(access & bus.we):
            with m.Switch(idx):
                with m.Case(0):
                    with m.If(~busy):
                        m.d.sync += [
                            shreg.eq(Cat(Const(0, 1), bus.dat_w[:8], Const(1, 1))),
                            bits_left.eq(10),
                            tick.eq(divisor - 1),
                        ]
                with m.Case(2):
                    m.d.sync += divisor.eq(bus.dat_w[:16])
        with m.If(access & ~bus.we):
            with m.Switch(idx):
                with m.Case(1):
                    m.d.sync += bus.dat_r.eq(busy)
                with m.Case(2):
                    m.d.sync += bus.dat_r.eq(divisor)
                with m.Default():
                    m.d.sync += bus.dat_r.eq(0)
        return m
