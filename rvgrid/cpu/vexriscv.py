"""VexRiscv as an Amaranth component.

The core is a pre-generated Verilog file (see ``vendor/vexriscv``) wrapped
with ``Instance``. Amaranth can't simulate it, so it only runs in the
Verilator/Icarus system tests; unit tests build a tile without a CPU.

The wrapper does two jobs besides wiring ports:

* ``hold`` keeps the core in reset while the rest of the tile runs (boot flow).
* VexRiscv's Wishbone bridges finish a transfer on ACK only and ignore ERR, so
  a transfer that ends in ERR would stall the core forever. The wrapper turns
  ERR into ACK. The tile records the error (TILECTRL.BUSERR_*) and the load
  returns 0.
"""

import re
from pathlib import Path

from amaranth import ClockSignal, Const, Instance, Module, ResetSignal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ..bus import wishbone

VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor" / "vexriscv"

VARIANTS = {
    # name: (file, gcc -march, short description)
    "min": ("VexRiscv_Min.v", "rv32i_zicsr", "RV32I, no caches, no prediction"),
}


def vexriscv_sources(variant, out_dir):
    """Copy the vendored Verilog into ``out_dir`` with unique module names.

    Every VexRiscv variant names its top module ``VexRiscv`` (plus helpers
    like ``StreamFifo``). Prefixing them lets different variants coexist in
    one multi-core design: ``VexRiscv`` -> ``VexRiscv_Min``,
    ``StreamFifo`` -> ``VexRiscv_Min_StreamFifo``.
    """
    file = VARIANTS[variant][0]
    module_name = Path(file).stem
    text = (VENDOR_DIR / file).read_text()
    names = re.findall(r"^module\s+(\w+)", text, flags=re.M)
    for name in names:
        new = module_name if name == "VexRiscv" else f"{module_name}_{name}"
        # "module Name (" declarations and "Name inst_name (" instantiations.
        text = re.sub(rf"^(\s*module\s+){name}\b", rf"\g<1>{new}", text, flags=re.M)
        text = re.sub(rf"^(\s*){name}(\s+\w+\s*[(#])", rf"\g<1>{new}\g<2>", text, flags=re.M)
    out = Path(out_dir) / file
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text() != text:
        out.write_text(text)
    return [out]


class VexRiscv(wiring.Component):
    ibus: Out(wishbone.Signature())
    dbus: Out(wishbone.Signature())
    hold: In(1)
    timer_irq: In(1)
    soft_irq: In(1)
    ext_irq: In(32)

    def __init__(self, variant="min", reset_vector=0):
        if variant not in VARIANTS:
            raise ValueError(f"unknown VexRiscv variant {variant!r}, have {list(VARIANTS)}")
        self.variant = variant
        self.reset_vector = reset_vector
        self.file, self.march, self.description = VARIANTS[variant]
        self.module_name = Path(self.file).stem
        super().__init__()

    def verilog_sources(self, out_dir):
        return vexriscv_sources(self.variant, out_dir)

    def elaborate(self, platform):
        m = Module()
        ib, db = self.ibus, self.dbus
        m.submodules.core = Instance(
            self.module_name,
            i_clk=ClockSignal(),
            i_reset=ResetSignal() | self.hold,
            i_externalResetVector=Const(self.reset_vector, 32),
            i_timerInterrupt=self.timer_irq,
            i_softwareInterrupt=self.soft_irq,
            i_externalInterruptArray=self.ext_irq,

            o_iBusWishbone_CYC=ib.cyc,
            o_iBusWishbone_STB=ib.stb,
            o_iBusWishbone_WE=ib.we,
            o_iBusWishbone_ADR=ib.adr,
            o_iBusWishbone_DAT_MOSI=ib.dat_w,
            o_iBusWishbone_SEL=ib.sel,
            i_iBusWishbone_DAT_MISO=ib.dat_r,
            i_iBusWishbone_ACK=ib.ack | ib.err,
            i_iBusWishbone_ERR=ib.err,

            o_dBusWishbone_CYC=db.cyc,
            o_dBusWishbone_STB=db.stb,
            o_dBusWishbone_WE=db.we,
            o_dBusWishbone_ADR=db.adr,
            o_dBusWishbone_DAT_MOSI=db.dat_w,
            o_dBusWishbone_SEL=db.sel,
            i_dBusWishbone_DAT_MISO=db.dat_r,
            i_dBusWishbone_ACK=db.ack | db.err,
            i_dBusWishbone_ERR=db.err,
        )
        return m
