"""A tile: one RISC-V core with its private memory and local peripherals.

    host/NoC ──► ┌───────────────────────── tile ─────────────────────────┐
                 │  core.ibus ─► fetch decoder ─────────► L1 port A        │
                 │  core.dbus ─┐                                           │
                 │             ├► arbiter ─► decoder ─┬─► L1 port B        │
                 │  host ──────┘                      ├─► TIMER ─► irq     │
                 │                                    ├─► TILECTRL ─► hold │
                 │                                    └─► ext ─────────────┼──► system bus
                 └─────────────────────────────────────────────────────────┘

The tile is the unit that gets replicated later (many tiles + a network on
chip, Tenstorrent style). Everything a core needs to run a kernel on its own
lives inside it. Shared things (console, DRAM, other tiles) are reached
through ``ext``, and the outside world reaches in through ``host``.
"""

from amaranth import C, Cat, Module, Mux
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, connect, flipped

from .bus import wishbone
from .bus.wishbone import Arbiter, Decoder
from .config import SYSTEM_WINDOW, SoCConfig, tile_regions
from .cpu.vexriscv import VexRiscv
from .mem.sram import SRAM
from .periph.tilectrl import TileCtrl
from .periph.timer import Timer


def image_to_words(image: bytes):
    """Little-endian 32-bit words, as the core sees memory."""
    image = image + b"\0" * (-len(image) % 4)
    return [int.from_bytes(image[i:i + 4], "little") for i in range(0, len(image), 4)]


class Tile(wiring.Component):
    host: In(wishbone.Signature())
    ext: Out(wishbone.Signature())

    def __init__(self, cfg: SoCConfig, tile_id=0, firmware: bytes | None = None, with_cpu=True):
        self.cfg = cfg
        self.tile_id = tile_id
        self.firmware = firmware
        self.with_cpu = with_cpu
        regions = {r.name: r for r in tile_regions(cfg)}
        self.l1_region = regions["L1"]
        self.regions = regions
        self.cpu = VexRiscv(cfg.cpu, reset_vector=self.l1_region.base) if with_cpu else None
        super().__init__()

    def verilog_sources(self, out_dir):
        return self.cpu.verilog_sources(out_dir) if self.cpu else []

    def elaborate(self, platform):
        m = Module()
        r = self.regions
        init = image_to_words(self.firmware) if self.firmware else ()

        m.submodules.l1 = l1 = SRAM(self.cfg.l1_size, init=init)
        m.submodules.timer = timer = Timer()
        # Without a baked-in image the core waits in reset for the host.
        m.submodules.ctrl = ctrl = TileCtrl(self.tile_id, hold_at_reset=self.firmware is None)

        # Data side: core + host share one decoder.
        m.submodules.arbiter = arb = Arbiter(2)
        m.submodules.decoder = dec = Decoder([
            ("l1", r["L1"].base, r["L1"].size),
            ("timer", r["TIMER"].base, r["TIMER"].size),
            ("ctrl", r["TILECTRL"].base, r["TILECTRL"].size),
            ("ext", SYSTEM_WINDOW.base, SYSTEM_WINDOW.size),
        ])
        connect(m, flipped(self.host), arb.m1)
        connect(m, arb.bus, dec.bus)
        connect(m, dec.l1, l1.dbus)
        connect(m, dec.timer, timer.bus)
        connect(m, dec.ctrl, ctrl.bus)
        connect(m, dec.ext, flipped(self.ext))

        # Fetch side: instructions come from L1 only.
        m.submodules.fetch = fetch = Decoder([("l1", r["L1"].base, r["L1"].size)])
        connect(m, fetch.l1, l1.ibus)

        if self.cpu is not None:
            m.submodules.cpu = cpu = self.cpu
            connect(m, cpu.ibus, fetch.bus)
            connect(m, cpu.dbus, arb.m0)
            m.d.comb += [
                cpu.hold.eq(ctrl.hold),
                cpu.timer_irq.eq(timer.irq),
            ]

        # Remember failed transfers (the core itself can't see them).
        d_err = dec.bus.err
        m.d.comb += [
            ctrl.buserr.eq(d_err | fetch.bus.err),
            ctrl.buserr_addr.eq(Mux(d_err, Cat(C(0, 2), dec.bus.adr),
                                    Cat(C(0, 2), fetch.bus.adr))),
        ]
        return m
