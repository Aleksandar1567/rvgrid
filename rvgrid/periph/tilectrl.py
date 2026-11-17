"""Tile control block: identity, core reset, bus-error capture.

* ``TILE_ID`` tells the firmware which tile it runs on. With many tiles all
  running the same binary, this is how each one picks its share of the work.
* ``CORE_CTRL.HOLD`` keeps the core in reset. A tile built without a baked-in
  firmware image powers up held; the host writes the program into L1 and then
  clears HOLD. This is the same boot flow a many-core accelerator uses.
* VexRiscv_Min ignores Wishbone ERR, so a bad address would otherwise go
  unnoticed. The tile records the first faulting address and counts errors.
"""

from amaranth import Module, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ..bus import wishbone
from ..bus.wishbone import register_slave
from .base import Reg


class TileCtrl(wiring.Component):
    REGS = (
        Reg("TILE_ID", 0x00, "ro", "Index of this tile"),
        Reg("SCRATCH", 0x04, "rw", "Free 32-bit register (host <-> core mailbox)"),
        Reg("CORE_CTRL", 0x08, "rw", "bit0 HOLD: 1 = core held in reset"),
        Reg("BUSERR_COUNT", 0x0C, "rw", "Bus errors seen (write any value to clear)"),
        Reg("BUSERR_ADDR", 0x10, "ro", "Byte address of the first bus error since clear"),
    )

    bus: In(wishbone.Signature())
    hold: Out(1)
    buserr: In(1)           # one-cycle pulse per failed transfer
    buserr_addr: In(32)     # byte address of that transfer

    def __init__(self, tile_id, hold_at_reset):
        self.tile_id = tile_id
        self.hold_at_reset = hold_at_reset
        super().__init__()

    def elaborate(self, platform):
        m = Module()
        bus = self.bus

        scratch = Signal(32)
        hold = Signal(init=int(self.hold_at_reset))
        err_count = Signal(32)
        err_addr = Signal(32)
        m.d.comb += self.hold.eq(hold)

        with m.If(self.buserr):
            m.d.sync += err_count.eq(err_count + 1)
            with m.If(err_count == 0):
                m.d.sync += err_addr.eq(self.buserr_addr)

        access = register_slave(m, bus)
        idx = bus.adr[:3]
        with m.If(access & bus.we):
            with m.Switch(idx):
                with m.Case(1):
                    m.d.sync += scratch.eq(bus.dat_w)
                with m.Case(2):
                    m.d.sync += hold.eq(bus.dat_w[0])
                with m.Case(3):
                    m.d.sync += [err_count.eq(0), err_addr.eq(0)]
        with m.If(access & ~bus.we):
            with m.Switch(idx):
                with m.Case(0):
                    m.d.sync += bus.dat_r.eq(self.tile_id)
                with m.Case(1):
                    m.d.sync += bus.dat_r.eq(scratch)
                with m.Case(2):
                    m.d.sync += bus.dat_r.eq(hold)
                with m.Case(3):
                    m.d.sync += bus.dat_r.eq(err_count)
                with m.Case(4):
                    m.d.sync += bus.dat_r.eq(err_addr)
                with m.Default():
                    m.d.sync += bus.dat_r.eq(0)
        return m
