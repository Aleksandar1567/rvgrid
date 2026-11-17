"""Wishbone B4 *classic* bus: signature, address decoder, round-robin arbiter.

Every bus in rvgrid uses the same shape: 32-bit data, byte granularity and a
30-bit *word* address (byte address >> 2). That is exactly what VexRiscv's
iBusWishbone/dBusWishbone ports use, so the CPU plugs in without adapters.

Handshake used everywhere (classic, one transfer per cycle-pair):

    cycle   0      1      2
    cyc   __/‾‾‾‾‾‾‾‾‾‾‾‾\\__
    stb   __/‾‾‾‾‾‾‾‾‾‾‾‾\\__
    ack   _________/‾‾‾‾‾\\__      slave answers one cycle after the request

A slave must assert ACK (or ERR) for exactly one cycle per request.
"""

from amaranth import Cat, Module, Mux, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

ADDR_WIDTH = 30
DATA_WIDTH = 32
SEL_WIDTH = DATA_WIDTH // 8


class Signature(wiring.Signature):
    """Wishbone master view. A slave port is ``In(Signature())``."""

    def __init__(self):
        super().__init__({
            "adr":   Out(ADDR_WIDTH),
            "dat_w": Out(DATA_WIDTH),
            "dat_r": In(DATA_WIDTH),
            "sel":   Out(SEL_WIDTH),
            "cyc":   Out(1),
            "stb":   Out(1),
            "we":    Out(1),
            "ack":   In(1),
            "err":   In(1),
        })

    def __eq__(self, other):
        return type(other) is Signature

    def __hash__(self):
        return hash(Signature)

    def __repr__(self):
        return "wishbone.Signature()"


def word_addr(byte_addr):
    return byte_addr >> 2


def register_slave(m, bus):
    """Standard slave handshake: registered one-cycle ACK.

    Returns the ``access`` strobe, high during the first cycle of a request.
    Do the write side effect (``access & bus.we``) and latch read data
    (``access & ~bus.we``) on it; ACK follows on the next cycle.
    """
    ack = Signal(name="ack_r")
    access = Signal(name="access")
    m.d.comb += access.eq(bus.cyc & bus.stb & ~ack)
    m.d.sync += ack.eq(access)
    m.d.comb += bus.ack.eq(ack)
    return access


class Decoder(wiring.Component):
    """Route one master to N slaves by address.

    ``regions`` is a list of ``(name, base, size)`` in *bytes*. ``size`` must
    be a power of two and ``base`` aligned to it. Each region becomes a master
    port named after it; slaves get the full word address and use the low bits
    they need.

    A request that hits no region is answered with ERR (one cycle), so a bad
    pointer can never hang the bus.
    """

    def __init__(self, regions):
        self.regions = []
        for name, base, size in regions:
            if size & (size - 1) or base % size:
                raise ValueError(f"region {name}: size must be 2^n and base aligned to it")
            self.regions.append((name, base, size))
        members = {"bus": In(Signature())}
        members.update({name: Out(Signature()) for name, _, _ in self.regions})
        super().__init__(members)

    def match(self, adr, base, size):
        """Combinational match of a word address against a byte region."""
        low_bits = (size.bit_length() - 1) - 2
        return (adr >> low_bits) == (base >> (low_bits + 2))

    def elaborate(self, platform):
        m = Module()
        bus = self.bus
        hits = []

        for name, base, size in self.regions:
            sub = getattr(self, name)
            hit = Signal(name=f"hit_{name}")
            m.d.comb += hit.eq(self.match(bus.adr, base, size))
            hits.append((hit, sub))
            m.d.comb += [
                sub.adr.eq(bus.adr),
                sub.dat_w.eq(bus.dat_w),
                sub.sel.eq(bus.sel),
                sub.we.eq(bus.we),
                sub.cyc.eq(bus.cyc & hit),
                sub.stb.eq(bus.stb & hit),
            ]

        # Responses: only the selected slave can answer.
        dat_r = 0
        ack = 0
        err = 0
        for hit, sub in hits:
            dat_r = Mux(hit, sub.dat_r, dat_r)
            ack = ack | (hit & sub.ack)
            err = err | (hit & sub.err)

        # Nobody home: answer with a single-cycle ERR.
        miss = Signal()
        miss_err = Signal()
        m.d.comb += miss.eq(~Cat(*(h for h, _ in hits)).any())
        m.d.sync += miss_err.eq(bus.cyc & bus.stb & miss & ~miss_err)

        m.d.comb += [
            bus.dat_r.eq(dat_r),
            bus.ack.eq(ack),
            bus.err.eq(err | miss_err),
        ]
        return m


class Arbiter(wiring.Component):
    """Share one bus between N masters, round-robin, one transfer at a time.

    Ownership is re-decided when the current owner finishes a transfer
    (ACK/ERR) or drops CYC, so one busy master cannot starve the others.
    Master ``mN`` ports are slave ports (``In``); ``bus`` is the shared master.
    """

    def __init__(self, n_masters):
        self.n = n_masters
        members = {f"m{i}": In(Signature()) for i in range(n_masters)}
        members["bus"] = Out(Signature())
        super().__init__(members)

    def masters(self):
        return [getattr(self, f"m{i}") for i in range(self.n)]

    def elaborate(self, platform):
        m = Module()
        masters = self.masters()
        grant = Signal(range(max(self.n, 2)))
        bus = self.bus

        # Forward the granted master.
        with m.Switch(grant):
            for i, mi in enumerate(masters):
                with m.Case(i):
                    m.d.comb += [
                        bus.adr.eq(mi.adr),
                        bus.dat_w.eq(mi.dat_w),
                        bus.sel.eq(mi.sel),
                        bus.we.eq(mi.we),
                        bus.cyc.eq(mi.cyc),
                        bus.stb.eq(mi.stb),
                    ]

        for i, mi in enumerate(masters):
            m.d.comb += [
                mi.dat_r.eq(bus.dat_r),
                mi.ack.eq(bus.ack & (grant == i)),
                mi.err.eq(bus.err & (grant == i)),
            ]

        # Re-arbitrate when the bus is free or the current transfer ends.
        release = ~bus.cyc | bus.ack | bus.err
        with m.If(release):
            with m.Switch(grant):
                for g in range(self.n):
                    with m.Case(g):
                        # Priority order starts with the master after g.
                        order = [(g + k) % self.n for k in range(1, self.n + 1)]
                        for j in reversed(order):
                            with m.If(masters[j].cyc):
                                m.d.sync += grant.eq(j)
        return m
