"""Render a window of a simulation VCD as an SVG timing diagram.

No dependencies: a streaming VCD reader plus a small SVG writer. Used by
``python -m rvgrid diagram`` to put real waveforms from the simulator into
the docs (``docs/img/wave_*.svg``).

Each row is sampled once per clock cycle, half a period after the rising
edge, which is the value the cycle "has" when the RTL samples it at the next edge.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from html import escape


@dataclass
class Row:
    label: str
    path: str                     # e.g. "rvgrid_soc.tile0.cpu.ibus__adr"
    fmt: callable = None          # int -> str for buses (default hex)
    clock: bool = False           # draw as a clock instead of sampled values
    valid: str = None             # path of a 1-bit row; value hidden while it is 0
    values: list = field(default_factory=list)


def _scan_header(f):
    """Return ({full.path.name: id}, timescale_in_ps)."""
    ids, scope, ts = {}, [], 1
    for line in f:
        t = line.split()
        if not t:
            continue
        if t[0] == "$scope":
            scope.append(t[2])
        elif t[0] == "$upscope":
            scope.pop()
        elif t[0] == "$var":
            ids.setdefault(".".join(scope + [t[4]]), t[3])
        elif t[0] == "$timescale":
            unit = t[1] if len(t) > 1 and t[1] != "$end" else next(f).split()[0]
            num = "".join(c for c in unit if c.isdigit()) or "1"
            ts = int(num) * {"fs": 1e-3, "ps": 1, "ns": 1e3, "us": 1e6}[unit.lstrip("0123456789")]
        elif t[0] == "$enddefinitions":
            break
    return ids, ts


def sample(vcd_path, clock, rows, start_when, n_cycles, pre_cycles=2):
    """Fill ``rows[i].values`` with one value per cycle for ``n_cycles`` cycles.

    ``start_when(path, value)`` is called on every change of a watched signal
    and returns True at the event the window starts from; ``pre_cycles``
    cycles before it are included.
    """
    changes = {r.path: [] for r in rows}
    rises = []
    with open(vcd_path) as f:
        ids, _ = _scan_header(f)
        by_id = {}
        for r in rows:
            by_id.setdefault(ids[r.path], []).append(r.path)
        clk_id = ids[clock]
        now, prev_clk, trigger, stop = 0, 0, None, None
        for line in f:
            c = line[0]
            if c == "#":
                now = int(line[1:])
                if stop is not None and now > stop:
                    break
                continue
            if c in "01xzXZ":
                bits, ident = c, line[1:].strip()
            elif c in "bB":
                bits, ident = line[1:].split()
            else:
                continue
            val = int(bits.translate(str.maketrans("xzXZ", "0000")), 2)
            if ident == clk_id:
                if val and not prev_clk:
                    rises.append(now)
                prev_clk = val
            for path in by_id.get(ident, ()):
                changes[path].append((now, val))
                if trigger is None and len(rises) >= 2 and start_when(path, val):
                    trigger = now
                    stop = now + (n_cycles + 4) * (rises[-1] - rises[-2])
    if trigger is None:
        raise ValueError("start event not found in the VCD")
    period = rises[1] - rises[0]
    first = bisect_right(rises, trigger) - 1 - pre_cycles
    for k in range(n_cycles + pre_cycles):
        t = rises[first + k] + period // 2
        for r in rows:
            times = [ct for ct, _ in changes[r.path]]
            i = bisect_right(times, t) - 1
            r.values.append(changes[r.path][i][1] if i >= 0 else 0)


CSS = """
text { font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; fill: #1f2328; }
.label { font-weight: 600; }
.wave { stroke: #0969da; stroke-width: 1.5; fill: none; }
.bus  { stroke: #8250df; stroke-width: 1.2; fill: #8250df14; }
.grid { stroke: #d0d7de; stroke-width: 0.5; }
.idle { stroke: #8c959f; stroke-width: 1; stroke-dasharray: 3 3; }
.title { font-size: 13px; font-weight: 700; }
@media (prefers-color-scheme: dark) {
  text { fill: #e6edf3; }
  .wave { stroke: #4493f8; }
  .bus  { stroke: #ab7df8; fill: #ab7df81f; }
  .grid { stroke: #30363d; }
  .idle { stroke: #6e7681; }
}
"""


def apply_valid(rows):
    """Replace values with None in cycles where the row's ``valid`` row is 0."""
    by_path = {r.path: r.values for r in rows}
    for r in rows:
        if r.valid:
            r.values = [v if ok else None for v, ok in zip(r.values, by_path[r.valid], strict=True)]


def render_svg(rows, title, cycle_w=26, row_h=26, label_w=190):
    apply_valid(rows)
    n = len(rows[0].values)
    width = label_w + n * cycle_w + 10
    height = 30 + len(rows) * row_h + 10
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}"><style>{CSS}</style>',
           f'<text class="title" x="8" y="18">{escape(title)}</text>']
    for k in range(n + 1):
        x = label_w + k * cycle_w
        out.append(f'<line class="grid" x1="{x}" y1="26" x2="{x}" y2="{height - 8}"/>')
    for ri, r in enumerate(rows):
        y0 = 30 + ri * row_h
        hi, lo = y0 + 4, y0 + row_h - 6
        out.append(f'<text class="label" x="8" y="{y0 + row_h / 2 + 3}">{escape(r.label)}</text>')
        if r.clock:
            half = cycle_w / 2
            pts = []
            for k in range(n):
                x0 = label_w + k * cycle_w
                pts += [f"{x0},{lo}", f"{x0},{hi}", f"{x0 + half},{hi}", f"{x0 + half},{lo}",
                        f"{x0 + cycle_w},{lo}"]
            out.append(f'<polyline class="wave" points="{" ".join(pts)}"/>')
        elif r.fmt is None and max(r.values, default=0) <= 1:
            pts = []
            for k, v in enumerate(r.values):
                x0, x1 = label_w + k * cycle_w, label_w + (k + 1) * cycle_w
                y = hi if v else lo
                pts += [f"{x0},{y}", f"{x1},{y}"]
            out.append(f'<polyline class="wave" points="{" ".join(pts)}"/>')
        else:
            fmt = r.fmt or (lambda v: f"{v:x}")
            k = 0
            while k < n:
                j = k
                while j + 1 < n and r.values[j + 1] == r.values[k]:
                    j += 1
                x0, x1 = label_w + k * cycle_w + 2, label_w + (j + 1) * cycle_w - 2
                mid = (hi + lo) / 2
                if r.values[k] is None:
                    out.append(f'<line class="idle" x1="{x0 - 2}" y1="{mid}" x2="{x1 + 2}" y2="{mid}"/>')
                    k = j + 1
                    continue
                out.append(f'<polygon class="bus" points="{x0},{mid} {x0 + 3},{hi} {x1 - 3},{hi} '
                           f'{x1},{mid} {x1 - 3},{lo} {x0 + 3},{lo}"/>')
                text = fmt(r.values[k])
                if (x1 - x0) >= 7 * len(text) + 4:
                    out.append(f'<text x="{(x0 + x1) / 2}" y="{mid + 4}" text-anchor="middle">'
                               f'{escape(text)}</text>')
                k = j + 1
    out.append("</svg>")
    return "\n".join(out)
