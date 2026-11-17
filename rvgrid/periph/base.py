"""Register description shared by all memory-mapped peripherals.

Each peripheral lists its registers in a ``REGS`` class attribute. The same
list drives the RTL address decode, the generated C header (``soc.h``), the
docs and the diagrams, so the hardware and the software can't disagree.

All peripheral registers are 32 bits wide, word aligned, and are meant for
32-bit accesses (``lw``/``sw``); byte enables are ignored.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Reg:
    name: str
    offset: int
    access: str  # "rw", "ro", "wo"
    desc: str
    reset: int = 0

    @property
    def index(self):
        return self.offset >> 2
