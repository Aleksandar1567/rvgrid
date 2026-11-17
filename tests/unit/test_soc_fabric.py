"""The whole SoC without the CPU: everything the host port can reach.

The CPU is a Verilog black box that Amaranth can't simulate, so here the host
port plays the core's role. This covers both decoders, the arbiter, L1, the
tile/system split and the bus-error path in well under a second.
"""

from rvgrid.config import SoCConfig, region
from rvgrid.soc import SoC
from rvgrid.sim.amaranth_bfm import run, wb_read, wb_write

CFG = SoCConfig.for_sim()
L1 = region(CFG, "L1").base
CTRL = region(CFG, "TILECTRL").base
LEDS = region(CFG, "LEDS").base
SIMCTRL = region(CFG, "SIMCTRL").base


def test_host_loads_l1_and_releases_core():
    dut = SoC(CFG, with_cpu=False)

    async def tb(ctx):
        words = [0x0000_0013 + i for i in range(16)]
        for i, w in enumerate(words):
            assert (await wb_write(ctx, dut.host, L1 + 4 * i, w)).ack
        for i, w in enumerate(words):
            assert (await wb_read(ctx, dut.host, L1 + 4 * i)).data == w
        # Last word of L1 is reachable, the next address is not.
        assert (await wb_write(ctx, dut.host, L1 + CFG.l1_size - 4, 0xCAFE)).ack
        # No firmware baked in: core starts held, host releases it.
        assert (await wb_read(ctx, dut.host, CTRL + 0x8)).data == 1
        await wb_write(ctx, dut.host, CTRL + 0x8, 0)
        assert (await wb_read(ctx, dut.host, CTRL + 0x8)).data == 0

    run(dut, tb)


def test_system_bus_through_tile():
    dut = SoC(CFG, with_cpu=False)

    async def tb(ctx):
        await wb_write(ctx, dut.host, LEDS, 0xA5)
        assert ctx.get(dut.leds) == 0xA5
        assert not ctx.get(dut.sim_done)
        await wb_write(ctx, dut.host, SIMCTRL, 42)
        assert ctx.get(dut.sim_done) and ctx.get(dut.sim_code) == 42

    run(dut, tb)


def test_bus_errors_are_recorded():
    dut = SoC(CFG, with_cpu=False)

    async def tb(ctx):
        # Hole in the tile map, then a hole in the system map.
        assert (await wb_read(ctx, dut.host, 0x4000_0000)).err
        assert (await wb_read(ctx, dut.host, 0x1000_F000)).err
        assert (await wb_read(ctx, dut.host, CTRL + 0x0C)).data == 2
        assert (await wb_read(ctx, dut.host, CTRL + 0x10)).data == 0x4000_0000

    run(dut, tb)


def test_baked_firmware_starts_running():
    image = bytes(range(16))
    dut = SoC(CFG, firmware=image, with_cpu=False)

    async def tb(ctx):
        assert (await wb_read(ctx, dut.host, CTRL + 0x8)).data == 0   # not held
        assert (await wb_read(ctx, dut.host, L1 + 4)).data == 0x0706_0504

    run(dut, tb)
