"""cocotb drivers/monitors for the SoC's top-level pins.

* ``HostPort``   - Wishbone master on ``host__*``: what a PCIe/JTAG/NoC host
                   would do. Used to load firmware and peek at memory.
* ``UartMonitor`` - decodes the ``uart_tx`` line exactly like a terminal on
                   the other end of the serial cable.

Signals are driven and sampled at the falling clock edge, half a cycle away
from the rising edge where the RTL samples them. That sidesteps every
"did I read before or after the flop updated" race.
"""

from cocotb.triggers import ClockCycles, FallingEdge


class HostPort:
    def __init__(self, dut, prefix="host__"):
        self.clk = dut.clk
        self.s = {n: getattr(dut, prefix + n) for n in
                  ("adr", "dat_w", "dat_r", "sel", "cyc", "stb", "we", "ack", "err")}
        self.idle()

    def idle(self):
        for n in ("cyc", "stb", "we"):
            self.s[n].value = 0
        self.s["adr"].value = 0
        self.s["dat_w"].value = 0
        self.s["sel"].value = 0

    async def _transfer(self, byte_addr, we, data=0, sel=0xF, timeout=64):
        await FallingEdge(self.clk)
        s = self.s
        s["adr"].value = byte_addr >> 2
        s["dat_w"].value = data
        s["sel"].value = sel
        s["we"].value = we
        s["cyc"].value = 1
        s["stb"].value = 1
        for _ in range(timeout):
            await FallingEdge(self.clk)
            if s["ack"].value or s["err"].value:
                err = bool(s["err"].value)
                data = int(s["dat_r"].value)
                break
        else:
            raise TimeoutError(f"host bus: no ACK/ERR for 0x{byte_addr:08x}")
        self.idle()
        if err:
            raise IOError(f"host bus: ERR at 0x{byte_addr:08x}")
        return data

    async def write(self, byte_addr, data, sel=0xF):
        await self._transfer(byte_addr, 1, data, sel)

    async def read(self, byte_addr):
        return await self._transfer(byte_addr, 0)

    async def load(self, base, image: bytes):
        image = image + b"\0" * (-len(image) % 4)
        for i in range(0, len(image), 4):
            await self.write(base + i, int.from_bytes(image[i:i + 4], "little"))

    async def dump(self, base, size):
        out = bytearray()
        for i in range(0, size, 4):
            out += (await self.read(base + i)).to_bytes(4, "little")
        return bytes(out)


class UartMonitor:
    """8N1 receiver. ``divisor`` = clock cycles per bit, as in the UART."""

    def __init__(self, line, clk, divisor, on_line=None):
        self.line, self.clk, self.divisor = line, clk, divisor
        self.data = bytearray()
        self.framing_errors = 0
        self._partial = bytearray()
        self.on_line = on_line

    async def run(self):
        d = self.divisor
        while True:
            await FallingEdge(self.line)                 # start bit begins
            await ClockCycles(self.clk, d // 2)          # middle of start bit
            if self.line.value != 0:
                continue                                 # glitch
            byte = 0
            for k in range(8):
                await ClockCycles(self.clk, d)
                byte |= int(self.line.value) << k
            await ClockCycles(self.clk, d)
            if self.line.value != 1:
                self.framing_errors += 1
            self.data.append(byte)
            self._line_char(byte)

    def _line_char(self, byte):
        if byte == ord("\n"):
            if self.on_line:
                self.on_line(self._partial.decode(errors="replace"))
            self._partial.clear()
        else:
            self._partial.append(byte)

    @property
    def text(self):
        return self.data.decode(errors="replace")
