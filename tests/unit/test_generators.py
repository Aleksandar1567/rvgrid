"""Generated artefacts: CPU sources, Verilog top level, C header, linker map."""

import re

from rvgrid.config import SoCConfig, all_regions
from rvgrid.cpu.vexriscv import vexriscv_sources
from rvgrid.gen import c_header, generate_rtl, linker_memory


def test_vexriscv_modules_get_unique_names(tmp_path):
    (src,) = vexriscv_sources("min", tmp_path)
    text = src.read_text()
    modules = re.findall(r"^module\s+(\w+)", text, flags=re.M)
    assert modules[0] == "VexRiscv_Min"
    assert all(m.startswith("VexRiscv_Min") for m in modules)
    # Instantiations follow the rename.
    assert re.search(r"^\s*VexRiscv_Min_StreamFifoLowLatency\s+\w+\s*\(", text, flags=re.M)
    assert not re.search(r"^\s*(module\s+)?StreamFifo\w*\s+\w+\s*\(", text, flags=re.M)


def test_top_level_ports(tmp_path):
    top, cpu = generate_rtl(SoCConfig.for_sim(), out_dir=tmp_path)
    header = top.read_text().split(";", 1)[0]
    for port in ("clk", "rst", "host__adr", "host__ack", "uart_tx", "leds", "sim_done", "sim_code"):
        assert re.search(rf"\b{port}\b", header), port
    assert "VexRiscv_Min" in top.read_text()      # the core is instantiated


def test_header_has_every_register():
    cfg = SoCConfig()
    h = c_header(cfg)
    for r in all_regions(cfg):
        assert f"#define {r.name}_BASE" in h
        for reg in getattr(r.periph, "REGS", ()):
            addr = f"0x{r.base + reg.offset:08X}u"
            assert re.search(rf"#define {r.name}_{reg.name}\s+\(\*\(volatile unsigned int \*\){addr}\)", h)


def test_linker_map_matches_l1():
    cfg = SoCConfig(l1_size=16 * 1024)
    assert "ORIGIN = 0x00000000, LENGTH = 0x4000" in linker_memory(cfg)
