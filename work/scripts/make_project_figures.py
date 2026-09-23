#!/usr/bin/env python3
"""Draw the portfolio's data figures as inline SVG, from each project's own numbers.

Three project cards carry a chart drawn here rather than a screenshot of a report:

  lmm     Linear Multistep Methods — recomputed from scratch: Method A,
          Y_{n+2} + 4Y_{n+1} - 5Y_n = h(4 f_{n+1} + 2 f_n), on y' = -y, h = 0.1,
          exactly as the repository's experiments/ex01_method_a.py sets it up.
  pinns   Neural Networks and PINNs — the committed training history of
          experiment 3 (spectral bias), copied into work/portfolio/figure-data/.
  ppa     Proximal Point Algorithms — the LASSO traces from the repository's
          lasso_iappa.py, with final gaps checked equal to its committed summary,
          and the bound-verification columns as committed. Also in figure-data/.

Every JSON in figure-data/ carries a _source line naming the repository, commit and
script it came from. Drawn inline, the charts use the page's own fonts and palette,
and their curves draw themselves on as the card scrolls into view.

    python3 work/scripts/make_project_figures.py            # rewrite the figures in the page
    python3 work/scripts/make_project_figures.py --check    # fail if any is stale

Everything between a figure:NAME:start / figure:NAME:end pair of comments in
docs/portfolio/index.html is generated here; do not edit it by hand.
"""
import argparse
import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "portfolio" / "index.html"
DATA = ROOT / "work" / "portfolio" / "figure-data"

INK, NAVY, SLATE, MUTED, GRID, PAPER = "#111111", "#1c2d3d", "#6d8397", "#5f6469", "#e3e1dc", "#ffffff"
SANS = "'Be Vietnam Pro', system-ui, sans-serif"
SERIF = "'Playfair Display', Georgia, serif"


# ── drawing primitives ────────────────────────────────────────────────────────

class Panel:
    """A plot area with optional log axes, mapping data to SVG coordinates."""

    def __init__(self, box, xlim, ylim, xlog=False, ylog=False):
        self.x0, self.y0, self.x1, self.y1 = box
        self.xlim, self.ylim, self.xlog, self.ylog = xlim, ylim, xlog, ylog

    def _t(self, v, lim, log):
        lo, hi = lim
        if log:
            v, lo, hi = math.log10(v), math.log10(lo), math.log10(hi)
        return (v - lo) / (hi - lo)

    def x(self, v):
        return self.x0 + self._t(v, self.xlim, self.xlog) * (self.x1 - self.x0)

    def y(self, v):
        return self.y1 - self._t(v, self.ylim, self.ylog) * (self.y1 - self.y0)

    def path(self, xs, ys):
        pts = [f"{self.x(a):.1f},{self.y(b):.1f}" for a, b in zip(xs, ys)]
        return "M" + " L".join(pts)


def power(k):
    """10 with a raised exponent, as SVG text."""
    if k == 0:
        return "1"
    sign = "−" if k < 0 else ""
    return f'10<tspan dy="-8" font-size="11">{sign}{abs(k)}</tspan>'


def open_svg(w, h, label_id, title, desc):
    return [
        f'<svg class="dfig-panel" viewBox="0 0 {w} {h}" role="img" aria-labelledby="{label_id}-t {label_id}-d" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="{SANS}" font-size="14" fill="{MUTED}">',
        f'<title id="{label_id}-t">{title}</title>',
        f'<desc id="{label_id}-d">{desc}</desc>',
        f'<rect width="{w}" height="{h}" fill="{PAPER}"/>',
    ]


def heading(x, title, sub):
    return [f'<text x="{x}" y="34" font-family="{SERIF}" font-weight="700" font-size="21" fill="{INK}">{title}</text>',
            f'<text x="{x}" y="58">{sub}</text>']


def grid(p, yticks, ylabel, xticks, xlabel_fmt=lambda v: f"{v:g}", xtitle=""):
    out = []
    for v in yticks:
        yy = p.y(v)
        out.append(f'<line x1="{p.x0}" x2="{p.x1}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{p.x0 - 10}" y="{yy + 5:.1f}" text-anchor="end">{ylabel(v)}</text>')
    for v in xticks:
        xx = p.x(v)
        out.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{p.y1}" y2="{p.y1 + 5}" stroke="{INK}"/>')
        out.append(f'<text x="{xx:.1f}" y="{p.y1 + 24}" text-anchor="middle">{xlabel_fmt(v)}</text>')
    out.append(f'<line x1="{p.x0}" x2="{p.x1}" y1="{p.y1}" y2="{p.y1}" stroke="{INK}"/>')
    if xtitle:
        out.append(f'<text x="{p.x1}" y="{p.y1 + 48}" text-anchor="end" font-style="italic">{xtitle}</text>')
    return out


def line(p, xs, ys, color, width, dash=None, cls="dfig-line", delay=0.0):
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path class="{cls}" d="{p.path(xs, ys)}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{extra}/>')


def sweep(p, uid, h):
    """Open a group whose clip rectangle sweeps left to right when the card scrolls in.

    A clip rather than a stroke-dash trick, so dashed series keep their dashes."""
    return (f'<defs><clipPath id="sw-{uid}"><rect class="dfig-sweep" x="{p.x0 - 8}" y="0" '
            f'width="{p.x1 - p.x0 + 16}" height="{h}"/></clipPath></defs><g clip-path="url(#sw-{uid})">')


def end_labels(p, items, gap=17):
    """Direct labels at the right end of each curve, pushed apart so none overlap.

    items: (y_svg, text, color). Returns SVG text elements."""
    items = sorted(items, key=lambda it: it[0])
    placed = []
    for y, text, color in items:
        if placed and y - placed[-1][0] < gap:
            y = placed[-1][0] + gap
        placed.append((y, text, color))
    # if the stack ran off the bottom, slide it back up as a block
    overflow = placed[-1][0] - (p.y1 - 4) if placed else 0
    if overflow > 0:
        placed = [(y - overflow, t, c) for y, t, c in placed]
    return [f'<text class="dfig-note" x="{p.x1 + 10}" y="{y + 5:.1f}" fill="{c}" font-weight="600">{t}</text>'
            for y, t, c in placed]


def wrap(name, panels, cols):
    body = "\n".join(panels)
    return f'<div class="dfig" style="--cols:{cols}" data-figure="{name}">\n{body}\n</div>'


# ── lmm: Method A diverges ───────────────────────────────────────────────────

def lmm():
    h, T = 0.1, 6.0
    n = round(T / h)
    t = [i * h for i in range(n + 1)]
    y = [1.0, math.exp(-h)]
    for k in range(n - 1):                       # alpha = (-5, 4, 1), beta = (2, 4, 0)
        f0, f1 = -y[k], -y[k + 1]
        y.append(-(4.0 * y[k + 1] - 5.0 * y[k]) + h * (4.0 * f1 + 2.0 * f0))
    exact = [math.exp(-s) for s in t]
    err = [abs(a - b) for a, b in zip(y, exact)]
    growth = err[-1] / err[-2]
    cross = t[next(i for i, e in enumerate(err) if e > 1)]
    top = math.floor(math.log10(abs(y[-1])))

    def symlog(v):
        return math.copysign(math.log10(1.0 + abs(v)), v)

    W, H = 500, 430
    xt = [0, 1, 2, 3, 4, 5, 6]

    a = Panel((86, 90, 470, 350), (0, 6), (-44, 44))
    pa = open_svg(W, H, "lmm-a", "Method A: the computed solution",
                  f"y′ = −y with step h = 0.1. The exact solution e to the minus t stays flat near zero; the "
                  f"computed one flips sign every step and grows to about 10 to the {top} by t = 6.")
    pa += heading(a.x0, "The computed solution", "signed log scale, sign(y)·log₁₀(1 + |y|)")
    pa += grid(a, [-40, -20, 0, 20, 40],
               lambda v: "0" if v == 0 else ("+" if v > 0 else "−") + power(abs(int(v))), xt, xtitle="t")
    pa.append(sweep(a, "lmm-a", H))
    pa.append(line(a, t, [symlog(v) for v in y], NAVY, 1.7))
    pa.append(line(a, t, [symlog(v) for v in exact], INK, 2.6))
    pa.append("</g>")
    lx, ly = a.x0 + 16, a.y0 + 16
    pa += [f'<rect x="{lx - 10}" y="{ly - 16}" width="196" height="54" fill="{PAPER}" opacity=".94"/>',
           f'<line x1="{lx}" x2="{lx + 26}" y1="{ly - 2}" y2="{ly - 2}" stroke="{INK}" stroke-width="2.6"/>',
           f'<text x="{lx + 36}" y="{ly + 3}" fill="{INK}">exact, e<tspan dy="-8" font-size="11">−t</tspan></text>',
           f'<line x1="{lx}" x2="{lx + 26}" y1="{ly + 24}" y2="{ly + 24}" stroke="{NAVY}" stroke-width="1.7"/>',
           f'<text x="{lx + 36}" y="{ly + 29}" fill="{INK}">Method A, h = {h:g}</text>', "</svg>"]

    b = Panel((86, 90, 470, 350), (0, 6), (1e-20, 1e44), ylog=True)
    logerr = [max(e, 1e-18) for e in err]      # the report floors the exact start (error 0) the same way
    pb = open_svg(W, H, "lmm-b", "Method A: the error",
                  f"The error on a log axis climbs in a straight line, multiplied by {growth:.2f} every step; "
                  f"it passes 1 at t = {cross:.1f} and reaches about 10 to the {top} by t = 6.")
    pb += heading(b.x0, "The error", "|Yₙ − y(tₙ)|, log scale")
    pb += grid(b, [1e-20, 1, 1e20, 1e40], lambda v: power(round(math.log10(v))), xt, xtitle="t")
    y1 = b.y(1)
    pb += [f'<line x1="{b.x0}" x2="{b.x1}" y1="{y1:.1f}" y2="{y1:.1f}" stroke="{SLATE}" stroke-width="1.3" stroke-dasharray="4 4"/>',
           f'<text x="{b.x1}" y="{y1 + 20:.1f}" text-anchor="end" fill="{SLATE}">error = 1, passed at t = {cross:.1f}</text>']
    pb.append(sweep(b, "lmm-b", H))
    pb.append(line(b, t, logerr, NAVY, 2.6))
    pb.append("</g>")
    ex, ey = b.x(t[-1]), b.y(logerr[-1])
    pb += [f'<circle class="dfig-note" cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="{NAVY}"/>',
           f'<text class="dfig-note" x="{ex - 14:.1f}" y="{ey - 14:.1f}" text-anchor="end" font-family="{SERIF}" '
           f'font-weight="700" font-size="17" fill="{INK}">×{growth:.2f} every step</text>', "</svg>"]
    return wrap("lmm", ["\n".join(pa), "\n".join(pb)], 2)


# ── pinns: spectral bias, and how the loss reverses it ───────────────────────

def pinns():
    d = json.loads((DATA / "pinns_spectral.json").read_text())
    runs = d["runs"]
    titles = {"regression": ("Plain regression", "low frequency learned first"),
              "residual": ("PINN residual loss", "the operator reverses the order"),
              "fourier": ("Residual + Fourier features", "high frequencies first, k = 1 last")}
    styles = {"1": (INK, 2.8, None), "4": (NAVY, 2.2, None), "8": (SLATE, 2.2, "6 5")}

    panels = []
    for i, mode in enumerate(["regression", "residual", "fourier"]):
        r = runs[mode]
        it = r["iters"]
        p = Panel((78, 92, 372, 330), (0, 8000), (1e-5, 10), ylog=True)
        title, sub = titles[mode]
        finals = ", ".join(f"k = {k}: {r['c'][k][-1]:.1e}" for k in ("1", "4", "8"))
        svg = open_svg(440, 400, f"pinn-{mode}", f"{title}: error per frequency during training",
                       f"Error coefficient of each frequency k = 1, 4, 8 over 8,000 Adam steps, log scale. "
                       f"Final values {finals}; relative L2 error {r['eps_L2']:.3g}.")
        svg += heading(p.x0, title, f"{sub} · rel. L² error {r['eps_L2']:.2g}")
        svg += grid(p, [1e-4, 1e-2, 1], lambda v: power(round(math.log10(v))), [0, 4000, 8000],
                    lambda v: f"{int(v):,}", xtitle="Adam steps")
        labels = []
        svg.append(sweep(p, f"pinn-{mode}", 400))
        for j, k in enumerate(("1", "4", "8")):
            color, width, dash = styles[k]
            ys = [min(max(v, 1e-5), 10) for v in r["c"][k]]
            svg.append(line(p, it, ys, color, width, dash))
            labels.append((p.y(ys[-1]), f"k = {k}", color))
        svg.append("</g>")
        svg += end_labels(p, labels)
        svg.append("</svg>")
        panels.append("\n".join(svg))
    return wrap("pinns", panels, 3)


# ── ppa: which inner schedules keep the rate, and the bound, checked ─────────

def ppa():
    d = json.loads((DATA / "ppa_lasso.json").read_text())
    S = d["schedules"]
    ks = d["k"]
    floor = 1e-10

    a = Panel((86, 90, 400, 350), (1, 120), (floor, 1e2), xlog=True, ylog=True)
    pa = open_svg(500, 430, "ppa-a", "Inexact accelerated PPA on LASSO: gap per outer step",
                  "F(x_k) minus F-star on log–log axes for four inner-accuracy schedules and the classical, "
                  "unaccelerated method, against O(1/k) and O(1/k squared) reference rates. "
                  + "; ".join(f"{S[s]['label']} ends at {S[s]['gap'][-1]:.1e}" for s in ("S1", "S2", "S4", "S5", "classical")) + ".")
    pa += heading(a.x0, "Which schedules keep the rate", "F(xₖ) − F*, log–log")
    pa += grid(a, [1e-10, 1e-6, 1e-2, 1e2], lambda v: power(round(math.log10(v))), [1, 10, 100],
               xtitle="outer step k")
    g0 = S["S5"]["gap"][1]
    ref_k = [1, 120]
    pa += [line(a, ref_k, [g0 / k for k in ref_k], GRID.replace("e3e1dc", "b9b5ab"), 1.2, "3 5", cls="dfig-ref"),
           line(a, ref_k, [g0 / k ** 2 for k in ref_k], GRID.replace("e3e1dc", "b9b5ab"), 1.2, "3 5", cls="dfig-ref"),
           f'<text x="{a.x(40):.1f}" y="{a.y(g0 / 40) - 8:.1f}" fill="#8a8f94" font-size="13">O(1/k)</text>',
           f'<text x="{a.x(40):.1f}" y="{a.y(g0 / 1600) - 8:.1f}" fill="#8a8f94" font-size="13">O(1/k²)</text>']
    series = [("S1", "T = 1", SLATE, 2.0, "7 5"), ("S2", "T = 4", SLATE, 2.2, None),
              ("S4", "√k", NAVY, 2.4, None), ("S5", "exact", INK, 2.6, None),
              ("classical", "classical", INK, 1.8, "2 5")]
    labels = []
    pa.append(sweep(a, "ppa-a", 430))
    for i, (key, name, color, width, dash) in enumerate(series):
        xs, ys = ks[1:], [max(v, floor) for v in S[key]["gap"][1:]]
        pa.append(line(a, xs, ys, color, width, dash))
        labels.append((a.y(ys[-1]), name, color))
    pa.append("</g>")
    pa += end_labels(a, labels)
    pa.append("</svg>")

    B = d["bounds"]
    v = d["violations"]
    b = Panel((86, 90, 440, 350), (0, 120), (1e-10, 1e2), ylog=True)
    pb = open_svg(500, 430, "ppa-b", "The convergence bound, checked at every step",
                  f"For the square-root schedule, the actual gap F(x_k) minus F-star against the report's two "
                  f"bounds over {v['steps']} outer steps: it stays below both, {v['type1']} and {v['type2']} violations.")
    pb += heading(b.x0, "The bound, checked", f"√k schedule · {v['type1'] + v['type2']} violations in {v['steps']} steps")
    pb += grid(b, [1e-10, 1e-6, 1e-2, 1e2], lambda v_: power(round(math.log10(v_))), [0, 40, 80, 120],
               xtitle="outer step k")
    pb.append(sweep(b, "ppa-b", 430))
    pb.append(line(b, B["k"], B["type1"], SLATE, 2.0, "7 5"))
    pb.append(line(b, B["k"], B["type2"], SLATE, 2.0))
    pb.append(line(b, B["k"], [max(x, 1e-10) for x in B["gap_S4"]], NAVY, 2.6))
    pb.append("</g>")
    lx, ly = b.x0 + 16, b.y1 - 70
    pb += [f'<rect x="{lx - 10}" y="{ly - 18}" width="200" height="80" fill="{PAPER}" opacity=".94"/>']
    for j, (label, color, width, dash) in enumerate([("actual gap", NAVY, 2.6, None),
                                                     ("bound, type 1", SLATE, 2.0, "7 5"),
                                                     ("bound, type 2", SLATE, 2.0, None)]):
        yy = ly + 24 * j
        dd = f' stroke-dasharray="{dash}"' if dash else ""
        pb += [f'<line x1="{lx}" x2="{lx + 26}" y1="{yy - 4}" y2="{yy - 4}" stroke="{color}" stroke-width="{width}"{dd}/>',
               f'<text x="{lx + 36}" y="{yy + 1}" fill="{INK}">{label}</text>']
    pb.append("</svg>")
    return wrap("ppa", ["\n".join(pa), "\n".join(pb)], 2)


# ── vietnam: the country in the hero panel, archipelagos included ───────────

# Principal features of the two archipelagos, (lon, lat).
HOANG_SA = [(112.33, 16.83), (111.60, 16.53), (111.20, 15.78), (112.73, 16.67), (111.71, 16.45),
            (111.75, 16.30), (112.54, 16.97), (112.21, 16.94), (111.92, 16.07), (112.26, 16.58)]
TRUONG_SA = [(111.92, 8.64), (114.33, 11.43), (114.36, 10.18), (114.33, 9.88), (114.48, 10.38),
             (112.92, 7.87), (113.30, 8.10), (113.70, 8.97), (114.62, 8.85), (111.67, 8.67),
             (115.03, 10.75), (114.08, 11.05), (115.55, 9.72), (116.15, 10.19), (113.85, 10.95),
             (112.25, 7.55), (115.85, 7.90), (114.85, 9.35)]


def vietnam():
    data = json.loads((ROOT / "work" / "portfolio" / "og-map" / "countries.json").read_text(encoding="utf-8"))
    rings = next(r for name, r in data["region"] if name == "Vietnam")
    lon0, lon1, lat0, lat1 = 102.0, 117.0, 7.2, 23.6
    k = math.cos(math.radians(15.5))
    s = 17.0                                          # px per degree of latitude
    W, H = round((lon1 - lon0) * k * s) + 8, round((lat1 - lat0) * s) + 8

    def xy(lon, lat):
        return 4 + (lon - lon0) * k * s, 4 + (lat1 - lat) * s

    d = "".join("M" + "L".join(f"{xy(x, y)[0]:.1f},{xy(x, y)[1]:.1f}" for x, y in r) + "Z" for r in rings)
    out = [f'<svg class="vn-map" viewBox="0 0 {W} {H}" role="img" aria-labelledby="vn-t" xmlns="http://www.w3.org/2000/svg">',
           '<title id="vn-t">Map of Việt Nam, including the Hoàng Sa (Paracel) and Trường Sa (Spratly) archipelagos</title>',
           f'<path class="vn-land" d="{d}"/>']
    for pts, cls in [(HOANG_SA, "vn-hs"), (TRUONG_SA, "vn-ts")]:
        out.append(f'<g class="vn-isl {cls}">' + "".join(
            f'<circle cx="{xy(x, y)[0]:.1f}" cy="{xy(x, y)[1]:.1f}" r="1.9"/>' for x, y in pts) + "</g>")
    hx, hy = xy(112.0, 17.25)
    tx, ty = xy(114.0, 12.0)
    out += [f'<text class="vn-lab" x="{hx:.1f}" y="{hy:.1f}" text-anchor="middle">Hoàng Sa</text>',
            f'<text class="vn-lab" x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle">Trường Sa</text>',
            "</svg>"]
    return "\n".join(out)


FIGURES = {"lmm": lmm, "pinns": pinns, "ppa": ppa, "vietnam": vietnam}


def block(name, indent):
    lines = [f"<!-- figure:{name}:start — generated by work/scripts/make_project_figures.py, do not edit by hand -->",
             *FIGURES[name]().split("\n"),
             f"<!-- figure:{name}:end -->"]
    return "\n".join(indent + ln if ln else ln for ln in lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if any figure in the page is stale")
    args = ap.parse_args()

    page = PAGE.read_text(encoding="utf-8")
    new = page
    for name in FIGURES:
        pat = re.compile(rf"([ \t]*)<!-- figure:{name}:start.*?<!-- figure:{name}:end -->", re.S)
        m = pat.search(new)
        if not m:
            sys.exit(f"no figure:{name}:start / figure:{name}:end markers in docs/portfolio/index.html")
        new = new[:m.start()] + block(name, m.group(1)) + new[m.end():]

    if new == page:
        print("docs/portfolio/index.html: all figures current")
        return
    if args.check:
        sys.exit("docs/portfolio/index.html: figures are stale — run make_project_figures.py")
    PAGE.write_text(new, encoding="utf-8")
    print("docs/portfolio/index.html: figures rewritten (" + ", ".join(FIGURES) + ")")


if __name__ == "__main__":
    main()
