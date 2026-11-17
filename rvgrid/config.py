"""SoC parameters and the memory map: the single source of truth.

The RTL decoders, the generated C header and linker script, the docs and the
diagrams are all built from what is defined here.

Address space as seen by a core (every tile sees the same local map):

    0x0000_0000  L1        tile    on-chip SRAM: code, data, stack
    0x0200_0000  TIMER     tile    mtime / mtimecmp
    0x0200_1000  TILECTRL  tile    tile id, core reset, bus errors
    0x1000_0000  UART      system  console
    0x1000_1000  LEDS      system  8 output pins
    0x1000_2000  SIMCTRL   system  end-of-simulation exit code

Anything in 0x1000_0000..0x1FFF_FFFF leaves the tile through its ``ext``
port and is decoded by the system bus. Everything else is a bus error.
"""

from dataclasses import dataclass, replace

from .periph.leds import LEDs
from .periph.simctrl import SimCtrl
from .periph.tilectrl import TileCtrl
from .periph.timer import Timer
from .periph.uart import UART

KiB = 1024
MiB = 1024 * KiB


@dataclass(frozen=True)
class Region:
    name: str
    base: int
    size: int
    scope: str              # "tile" (private per tile) or "system" (shared)
    desc: str
    periph: type | None = None   # class with REGS, None for memories

    @property
    def end(self):
        return self.base + self.size - 1


@dataclass(frozen=True)
class SoCConfig:
    clk_hz: int = 50_000_000
    l1_size: int = 32 * KiB
    uart_baud: int = 115_200
    uart_divisor: int | None = None     # cycles per bit; None = clk_hz // uart_baud
    cpu: str = "min"                    # VexRiscv variant, see rvgrid/cpu/vexriscv.py

    @property
    def divisor(self):
        return self.uart_divisor or self.clk_hz // self.uart_baud

    @classmethod
    def for_sim(cls, **kw):
        """Same hardware, but the UART runs at 8 cycles/bit so printing is cheap."""
        return replace(cls(), uart_divisor=8, **kw)


SYSTEM_WINDOW = Region("SYSTEM", 0x1000_0000, 256 * MiB, "tile",
                       "Window to the shared system bus (leaves the tile)")


def tile_regions(cfg: SoCConfig):
    return [
        Region("L1", 0x0000_0000, cfg.l1_size, "tile", "Dual-port SRAM: code, data, stack"),
        Region("TIMER", 0x0200_0000, 4 * KiB, "tile", "Machine timer (mtime / mtimecmp)", Timer),
        Region("TILECTRL", 0x0200_1000, 4 * KiB, "tile", "Tile id, core reset, bus errors", TileCtrl),
    ]


def system_regions(cfg: SoCConfig):
    return [
        Region("UART", 0x1000_0000, 4 * KiB, "system", "Console (8N1 transmitter)", UART),
        Region("LEDS", 0x1000_1000, 4 * KiB, "system", "8 output pins", LEDs),
        Region("SIMCTRL", 0x1000_2000, 4 * KiB, "system", "Simulation exit code", SimCtrl),
    ]


def all_regions(cfg: SoCConfig):
    return tile_regions(cfg) + system_regions(cfg)


def region(cfg: SoCConfig, name: str) -> Region:
    for r in all_regions(cfg):
        if r.name == name:
            return r
    raise KeyError(name)
