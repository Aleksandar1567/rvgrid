"""SRAM, UART, timer and tile control, each on its own."""

from rvgrid.mem.sram import SRAM
from rvgrid.periph.tilectrl import TileCtrl
from rvgrid.periph.timer import Timer
from rvgrid.periph.uart import UART
from rvgrid.sim.amaranth_bfm import run, wb_read, wb_write


def test_sram_byte_lanes_and_both_ports():
    dut = SRAM(1024, init=[0x1111_1111, 0x2222_2222])

    async def tb(ctx):
        # Init image is visible on the fetch port.
        assert (await wb_read(ctx, dut.ibus, 4)).data == 0x2222_2222
        # Full word, then single bytes and a half word through SEL.
        await wb_write(ctx, dut.dbus, 0x10, 0xAABB_CCDD)
        await wb_write(ctx, dut.dbus, 0x10, 0x0000_0011, sel=0b0001)
        await wb_write(ctx, dut.dbus, 0x10, 0x2200_0000, sel=0b1000)
        await wb_write(ctx, dut.dbus, 0x14, 0x0000_BEEF, sel=0b0011)
        assert (await wb_read(ctx, dut.dbus, 0x10)).data == 0x22BB_CC11
        assert (await wb_read(ctx, dut.dbus, 0x14)).data == 0x0000_BEEF
        # Port A sees port B's writes.
        assert (await wb_read(ctx, dut.ibus, 0x10)).data == 0x22BB_CC11

    run(dut, tb)


def decode_uart(samples, divisor):
    """Turn a per-cycle list of tx levels into bytes (8N1)."""
    out, i = [], 0
    while i < len(samples):
        if samples[i] == 0:                       # start bit
            mid = i + divisor // 2
            bits = [samples[mid + divisor * (k + 1)] for k in range(8)]
            assert samples[mid + divisor * 9] == 1, "missing stop bit"
            out.append(sum(b << k for k, b in enumerate(bits)))
            i = mid + divisor * 9
        i += 1
    return bytes(out)


def test_uart_sends_8n1_frames():
    divisor = 4
    dut = UART(divisor)
    samples = []

    async def tb(ctx):
        for ch in b"Hi":
            while (await wb_read(ctx, dut.bus, 0x4)).data & 1:
                pass
            r = await wb_write(ctx, dut.bus, 0x0, ch)
            assert r.ack
            assert (await wb_read(ctx, dut.bus, 0x4)).data == 1   # now busy
        for _ in range(divisor * 12):
            await ctx.tick()

    async def probe(ctx):
        async for _clk, _rst, tx in ctx.tick().sample(dut.tx):
            samples.append(tx)

    run(dut, tb, background=[probe])
    assert decode_uart(samples, divisor) == b"Hi"


def test_timer_interrupt_fires_at_compare():
    dut = Timer()

    async def tb(ctx):
        assert not ctx.get(dut.irq)              # mtimecmp resets to all ones
        now = (await wb_read(ctx, dut.bus, 0x0)).data
        await wb_write(ctx, dut.bus, 0xC, 0)
        await wb_write(ctx, dut.bus, 0x8, now + 20)
        assert not ctx.get(dut.irq)
        for _ in range(20):
            await ctx.tick()
        assert ctx.get(dut.irq)
        later = (await wb_read(ctx, dut.bus, 0x0)).data
        assert later > now + 20

    run(dut, tb)


def test_tilectrl_hold_and_buserr_capture():
    dut = TileCtrl(tile_id=7, hold_at_reset=True)

    async def tb(ctx):
        assert (await wb_read(ctx, dut.bus, 0x00)).data == 7
        assert ctx.get(dut.hold) == 1
        await wb_write(ctx, dut.bus, 0x08, 0)
        assert ctx.get(dut.hold) == 0
        # Two errors: count both, keep the first address.
        for addr in (0x4000_0000, 0x5000_0000):
            ctx.set(dut.buserr, 1)
            ctx.set(dut.buserr_addr, addr)
            await ctx.tick()
            ctx.set(dut.buserr, 0)
        assert (await wb_read(ctx, dut.bus, 0x0C)).data == 2
        assert (await wb_read(ctx, dut.bus, 0x10)).data == 0x4000_0000
        await wb_write(ctx, dut.bus, 0x0C, 0)
        assert (await wb_read(ctx, dut.bus, 0x0C)).data == 0

    run(dut, tb)
