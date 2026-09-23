#!/usr/bin/env python3
"""Render docs/portfolio/og.png — the 1200x630 social-share card for the portfolio.

This card is what LinkedIn and Facebook show when the portfolio link is posted, so
it is the first thing most readers see. It is generated, like the paper's card next
to it, and drawn in the site's own system: paper ground, ink and navy, the name in
Playfair Display, three facts about the whole body of work, and a world map with
Việt Nam picked out under a magnifier.

The map is drawn here from Natural Earth country outlines (public domain), vendored
as a small extract in work/portfolio/og-map/countries.json: the world at 1:110m, and
the region around Việt Nam at 1:50m for the magnified view. Hoàng Sa and Trường Sa
are marked as Vietnamese, as Vietnamese maps show them. To refresh the extract from
the world-atlas package (npm, which packages Natural Earth as TopoJSON):

    python3 work/scripts/make_portfolio_og.py --vendor-map path/to/world-atlas/package

The fonts are vendored in work/portfolio/fonts/ and embedded into the card, so it
renders the same with no network — and the script refuses to write the PNG if they
did not load, rather than quietly shipping a card set in a fallback face.

    pip install playwright && python3 work/scripts/make_portfolio_og.py
"""
import argparse
import base64
import json
import math
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "portfolio" / "og.png"
FONTS = ROOT / "work" / "portfolio" / "fonts"
MAP = ROOT / "work" / "portfolio" / "og-map" / "countries.json"

# The magnified view: everything inside this box, at 1:50m.
REGION = (96.0, 3.0, 121.0, 27.0)          # lon0, lat0, lon1, lat1 — the lens's field of view
LAND, LAND_LENS, SEA_LENS, VN_RED, VN_STAR = "#c4ced8", "#d9e0e7", "#eef3f6", "#da251d", "#ffde00"

CARD = """
<style>
  {fonts}
  *{{box-sizing:border-box; margin:0; padding:0}}
  body{{width:1200px; height:630px; padding:56px 64px 48px; display:flex; flex-direction:column;
       font-family:'Be Vietnam Pro', sans-serif; color:#111; background:#fbfbf9;
       -webkit-font-smoothing:antialiased}}
  .top{{display:flex; justify-content:space-between; align-items:center;
        font-size:16px; letter-spacing:.2em; text-transform:uppercase; color:#3d4247}}
  .top .url{{letter-spacing:.08em; text-transform:none; color:#5f6469}}
  .mid{{display:grid; grid-template-columns:500px 1fr; gap:24px; align-items:center; margin-top:26px}}
  h1{{font-family:'Playfair Display', serif; font-weight:900; font-size:100px;
     line-height:.98; letter-spacing:-.015em}}
  .line{{font-family:'Playfair Display', serif; font-weight:400; font-size:25px; line-height:1.4;
        color:#111; margin-top:24px; max-width:480px; text-wrap:balance}}
  .map svg{{display:block; width:100%; height:auto}}
  .stats{{margin-top:auto; display:grid; grid-template-columns:repeat(3, 1fr);
         border-top:1px solid #cfccc4; padding-top:22px}}
  .stat{{padding:0 28px; border-left:1px solid #e3e1dc; display:flex; gap:16px; align-items:baseline}}
  .stat:first-child{{padding-left:0; border-left:0}}
  .n{{font-family:'Playfair Display', serif; font-weight:900; font-size:44px; line-height:1}}
  .l{{font-size:16px; line-height:1.35; color:#3d4247}}
</style>
<div class="top"><span>Mathematics &times; Computer Science</span><span class="url">tu-h-nguyn.github.io</span></div>
<div class="mid">
  <div>
    <h1>Nguy&#7877;n<br>Ho&agrave;ng T&uacute;</h1>
    <p class="line">Machine learning, numerical methods and quantitative research &mdash; built from the mathematics up.</p>
  </div>
  <div class="map">{map}</div>
</div>
<div class="stats">
  <div class="stat"><div class="n">8</div><div class="l">public repositories,<br>every one with CI</div></div>
  <div class="stat"><div class="n">5</div><div class="l">re-derive their published<br>numbers on every push</div></div>
  <div class="stat"><div class="n">1</div><div class="l">theory thesis: why<br>PINNs fail, six experiments</div></div>
</div>
"""


# ── the map ──────────────────────────────────────────────────────────────────

def topo_countries(path):
    """[(name, [[ring, ...], ...])] from a world-atlas TopoJSON file, rings as (lon, lat)."""
    t = json.loads(pathlib.Path(path).read_text())
    (sx, sy), (tx, ty) = t["transform"]["scale"], t["transform"]["translate"]
    arcs = []
    for arc in t["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx):
        out = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(a if not out else a[1:])
        return out

    out = []
    for g in t["objects"]["countries"]["geometries"]:
        if g["type"] == "Polygon":
            polys = [[ring(r) for r in g["arcs"]]]
        elif g["type"] == "MultiPolygon":
            polys = [[ring(r) for r in p] for p in g["arcs"]]
        else:
            continue
        out.append((g["properties"]["name"], polys))
    return out


def clip(ring, box):
    """Sutherland–Hodgman: a ring clipped to an axis-aligned lon/lat box."""
    x0, y0, x1, y1 = box
    edges = [(lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
             (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1))]
    pts = ring
    for inside, cross in edges:
        if not pts:
            break
        src, pts = pts, []
        for i, cur in enumerate(src):
            prev = src[i - 1]
            if inside(cur):
                if not inside(prev):
                    pts.append(cross(prev, cur))
                pts.append(cur)
            elif inside(prev):
                pts.append(cross(prev, cur))
    return pts


def simplify(ring, tol):
    """Douglas–Peucker: drop points that move the outline by less than tol degrees."""
    if len(ring) < 5:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        i, j = stack.pop()
        (x1, y1), (x2, y2) = ring[i], ring[j]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-12
        best, idx = 0.0, None
        for k in range(i + 1, j):
            x, y = ring[k]
            d = abs(dy * (x - x1) - dx * (y - y1)) / norm if (dx or dy) else math.hypot(x - x1, y - y1)
            if d > best:
                best, idx = d, k
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [p for p, k in zip(ring, keep) if k]


def vendor_map(src):
    """Write the compact extract the card is drawn from."""
    src = pathlib.Path(src)
    # Tolerances are about half a pixel at the scale each part is drawn: ~1.8 px per
    # degree for the world, ~9 px per degree inside the lens.
    rnd = lambda ring, n: [[round(x, n), round(y, n)] for x, y in ring]
    world = []
    for name, polys in topo_countries(src / "countries-110m.json"):
        if name == "Antarctica":
            continue
        rings = [[rnd(simplify(r, 0.25), 1) for r in poly] for poly in polys]
        rings = [[r for r in poly if len(r) > 3] for poly in rings]
        world.append([name, [poly for poly in rings if poly]])
    region = []
    for name, polys in topo_countries(src / "countries-50m.json"):
        rings = [rnd(simplify(c, 0.04), 2) for poly in polys for c in [clip(poly[0], REGION)] if len(c) > 2]
        rings = [r for r in rings if len(r) > 3]
        if rings:
            region.append([name, rings])
    MAP.parent.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps({
        "_source": "Natural Earth admin-0 countries (public domain), via world-atlas 2.0.2 "
                   "(npm, ISC). world: 1:110m without Antarctica, simplified to 0.25 degree; region: "
                   f"1:50m clipped to lon/lat box {list(REGION)}, simplified to 0.04 degree. "
                   "Regenerate: make_portfolio_og.py --vendor-map <world-atlas package dir>.",
        "world": world, "region": region}, separators=(",", ":")), encoding="utf-8")
    print(f"{MAP.relative_to(ROOT)}  {MAP.stat().st_size // 1024} KB, "
          f"{len(world)} countries + {len(region)} in the magnified region")


def natural_earth(lon, lat):
    """The Natural Earth projection (Šavrič et al.), in radians-scaled units."""
    l, p = math.radians(lon), math.radians(lat)
    p2 = p * p
    p4 = p2 * p2
    x = l * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)))
    y = p * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)))
    return x, y


def unwrap(ring):
    """A ring that crosses the 180th meridian (Chukotka, Fiji) would draw a line
    across the whole map; fold its far side onto the meridian instead."""
    if not any(abs(a[0] - b[0]) > 180 for a, b in zip(ring, ring[1:])):
        return ring
    east = sum(1 for x, _ in ring if x > 0) >= len(ring) / 2
    return [(min(x + 360, 180) if east and x < 0 else max(x - 360, -180) if not east and x > 0 else x, y)
            for x, y in ring]


def path(rings, proj):
    d = []
    for r in map(unwrap, rings):
        pts = [proj(x, y) for x, y in r]
        d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
    return "".join(d)


def star(cx, cy, r):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.382
        pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
    return "M" + "L".join(pts) + "Z"


def map_svg():
    data = json.loads(MAP.read_text(encoding="utf-8"))
    W, H = 560, 360
    # world: Natural Earth projection scaled to the width, Antarctica left out
    xmax = natural_earth(180, 0)[0]
    ytop, ybot = natural_earth(0, 84)[1], natural_earth(0, -57)[1]
    k = (W - 4) / (2 * xmax)
    oy = H - 8 - (ytop - ybot) * k

    def world(lon, lat):
        x, y = natural_earth(lon, lat)
        return 2 + (x + xmax) * k, oy + (ytop - y) * k

    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
             f'aria-label="World map with Việt Nam highlighted and magnified">',
             '<defs><filter id="sh" x="-20%" y="-20%" width="140%" height="140%">'
             '<feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#1c2d3d" flood-opacity=".18"/></filter>'
             '<clipPath id="lens"><circle cx="0" cy="0" r="1"/></clipPath></defs>']
    for name, polys in data["world"]:
        fill = VN_RED if name == "Vietnam" else LAND
        d = "".join(path(poly, world) for poly in polys)
        parts.append(f'<path d="{d}" fill="{fill}" stroke="#fbfbf9" stroke-width=".5" fill-rule="evenodd"/>')

    # the magnifier: centred over Việt Nam itself, as a loupe laid on the map
    vx, vy = world(106.3, 16.0)
    R = 98
    cx, cy = min(vx - 6, W - R - 6), max(vy + 6, R + 44)
    # inside the lens: the region at 1:50m, equirectangular about its centre
    lon_c, lat_c = 108.2, 14.6
    s = R / 10.6                                   # pixels per degree of latitude
    cosl = math.cos(math.radians(lat_c))

    def local(lon, lat):
        return cx + (lon - lon_c) * s * cosl, cy - (lat - lat_c) * s

    parts.append(f'<g filter="url(#sh)"><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R}" fill="{SEA_LENS}"/></g>')
    parts.append(f'<clipPath id="lc"><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R - 1}"/></clipPath><g clip-path="url(#lc)">')
    for name, rings in data["region"]:
        fill = VN_RED if name == "Vietnam" else LAND_LENS
        parts.append(f'<path d="{path(rings, local)}" fill="{fill}" stroke="#ffffff" stroke-width=".8" stroke-linejoin="round"/>')
    # Hoàng Sa and Trường Sa, as Vietnamese maps show them
    for lon, lat in [(111.6, 16.5), (112.3, 16.8), (111.9, 16.2), (112.7, 16.5),
                     (114.3, 10.4), (113.8, 9.9), (114.9, 10.9), (112.8, 8.8), (115.6, 10.0)]:
        x, y = local(lon, lat)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="{VN_RED}"/>')
    parts.append("</g>")
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R}" fill="none" stroke="#ffffff" stroke-width="5"/>')
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R + 2.5}" fill="none" stroke="#cfccc4" stroke-width="1"/>')

    # the pin: the flag in a white ring, pointing into the lens
    px, py, pr = cx - 34, cy - R + 8, 25
    parts.append(f'<g filter="url(#sh)"><path d="M{px - 9:.1f},{py + pr - 3:.1f}L{px:.1f},{py + pr + 13:.1f}'
                 f'L{px + 9:.1f},{py + pr - 3:.1f}Z" fill="#ffffff"/>'
                 f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{pr + 5}" fill="#ffffff"/></g>')
    parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{pr}" fill="{VN_RED}"/>')
    parts.append(f'<path d="{star(px, py + 1.5, pr * 0.62)}" fill="{VN_STAR}"/>')

    # the caption, under the lens
    parts.append(f'<text x="{cx:.1f}" y="{cy + R + 24:.1f}" text-anchor="middle" font-family="Be Vietnam Pro" '
                 f'font-weight="600" font-size="15" letter-spacing="2.4" fill="#1c2d3d">VIỆT NAM</text>')
    parts.append("</svg>")
    return "".join(parts)


def font_css():
    """fonts.css with every url() replaced by the file itself, as a data URI."""
    css = (FONTS / "fonts.css").read_text(encoding="utf-8")

    def inline(m):
        data = base64.b64encode((FONTS / m.group(1)).read_bytes()).decode()
        return f"url(data:font/woff2;base64,{data})"

    return re.sub(r"url\(([^)]+\.woff2)\)", inline, css)


def chromium():
    for p in sorted(pathlib.Path("/opt/pw-browsers").glob("chromium*/chrome-linux/chrome")):
        return str(p)
    direct = pathlib.Path("/opt/pw-browsers/chromium")
    if direct.exists():
        return str(direct)
    return shutil.which("chromium") or shutil.which("google-chrome")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor-map", metavar="DIR", help="refresh the map extract from a world-atlas package directory")
    args = ap.parse_args()
    if args.vendor_map:
        vendor_map(args.vendor_map)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed — pip install playwright")

    html = CARD.format(fonts=font_css(), map=map_svg())

    with sync_playwright() as pw:
        exe = chromium()
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630},
                                device_scale_factor=1)
        page.set_content(html, wait_until="load")
        page.evaluate("document.fonts.ready")

        # A share card in a fallback face is worse than no new card at all. Check the
        # exact glyphs that matter — the Vietnamese marks in the name included.
        missing = page.evaluate("""() => [
            ["900 104px 'Playfair Display'", "Nguyễn Hoàng Tú 8 5 1"],
            ["400 26px 'Playfair Display'", "Machine learning, numerical methods and quantitative research — built from the mathematics up."],
            ["400 16px 'Be Vietnam Pro'", "MATHEMATICS × COMPUTER SCIENCE tu-h-nguyn.github.io public repositories, every one with CI"],
            ["600 15px 'Be Vietnam Pro'", "VIỆT NAM"],
        ].filter(([font, text]) => !document.fonts.check(font, text)).map(([f]) => f)""")
        # check() also answers true when no face matches at all, so separately require
        # that both families really loaded.
        loaded = set(page.evaluate("""() => [...document.fonts]
            .filter(f => f.status === 'loaded')
            .map(f => f.family.replace(/["']/g, ''))"""))
        absent = {"Playfair Display", "Be Vietnam Pro"} - loaded
        if missing or absent:
            browser.close()
            sys.exit(f"fonts did not load, card not written: {missing or sorted(absent)}")

        # Nothing may spill out of the card: every box has to sit inside 1200x630.
        spill = page.evaluate("""() => [...document.querySelectorAll('body *')]
            .filter(e => { const r = e.getBoundingClientRect();
                           return r.right > 1200.5 || r.bottom > 630.5; })
            .map(e => e.tagName + '.' + e.className)""")
        if spill:
            browser.close()
            sys.exit(f"card content overflows 1200x630: {spill}")

        page.screenshot(path=str(OUT))
        browser.close()

    print(f"{OUT.relative_to(ROOT)}  {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
