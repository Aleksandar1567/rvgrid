"""The top level: tiles + the shared system bus + the pins.

    host port ─────► tile0 ── ext ──► system decoder ──┬─► UART ────► uart_tx
                                                       ├─► LEDS ────► leds[7:0]
                                                       └─► SIMCTRL ─► sim_done / sim_code

One tile for now. Multi-tile versions replace the single ``ext`` link with an
arbiter or a network on chip (see docs/05-roadmap.md); tiles stay unchanged.

Top-level ports (Verilog names): clk, rst, host__* (Wishbone slave), uart_tx,
leds, sim_done, sim_code.
"""

from amaranth import Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, connect, flipped

from .bus import wishbone
from .bus.wishbone import Decoder
from .config import SoCConfig, system_regions
from .periph.leds import LEDs
from .periph.simctrl import SimCtrl
from .periph.uart import UART
from .tile import Tile


class SoC(wiring.Component):
    host: In(wishbone.Signature())
    uart_tx: Out(1, init=1)
    leds: Out(8)
    sim_done: Out(1)
    sim_code: Out(32)

    def __init__(self, cfg: SoCConfig | None = None, firmware: bytes | None = None,
                 with_cpu=True):
        cfg = cfg or SoCConfig()
        self.cfg = cfg
        self.tile = Tile(cfg, tile_id=0, firmware=firmware, with_cpu=with_cpu)
        super().__init__()

    def verilog_sources(self, out_dir):
        return self.tile.verilog_sources(out_dir)

    def elaborate(self, platform):
        m = Module()
        m.submodules.tile0 = tile = self.tile

        regions = {r.name: r for r in system_regions(self.cfg)}
        m.submodules.sysbus = sysbus = Decoder(
            [(n.lower(), r.base, r.size) for n, r in regions.items()])
        m.submodules.uart = uart = UART(self.cfg.divisor)
        m.submodules.led = leds = LEDs()
        m.submodules.simctrl = simctrl = SimCtrl()

        connect(m, flipped(self.host), tile.host)
        connect(m, tile.ext, sysbus.bus)
        connect(m, sysbus.uart, uart.bus)
        connect(m, sysbus.leds, leds.bus)
        connect(m, sysbus.simctrl, simctrl.bus)

        m.d.comb += [
            self.uart_tx.eq(uart.tx),
            self.leds.eq(leds.pins),
            self.sim_done.eq(simctrl.done),
            self.sim_code.eq(simctrl.code),
        ]
        return m
