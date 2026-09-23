#!/usr/bin/env python3
"""Static audit of every portfolio page in docs/portfolio/ — links, contrast, SEO, assets.

Runs offline against the built files (build_portfolio.py writes them), so it checks
exactly what gets published:

  links     every in-page and cross-page link resolves, down to the #anchor;
            every target=_blank carries rel=noopener; no href="#"
  assets    every local src/href exists; the share image is 1200x630
  contrast  every text colour on every ground it sits on, light AND dark theme
  SEO       per page: title, description, canonical, Open Graph, one <h1>;
            JSON-LD on the home page

    python3 work/scripts/audit_portfolio.py
"""
import json
import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "docs" / "portfolio"
PAGES = sorted(SITE.rglob("index.html"))

issues = []


def fail(msg):
    issues.append(msg)


def rel(p):
    return p.relative_to(ROOT).as_posix()


def strip_comments(html):
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def ids_of(path, cache={}):
    if path not in cache:
        cache[path] = set(re.findall(r'\sid="([^"]+)"', path.read_text(encoding="utf-8")))
    return cache[path]


def resolve(page, href):
    """A local href -> (file on disk, fragment). Directory links mean their index.html."""
    path, _, frag = href.partition("#")
    if not path:
        return page, frag
    target = (page.parent / path).resolve()
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target, frag


# ── links and assets, page by page ───────────────────────────────────────────
print("links and assets:")
for page in PAGES:
    html = strip_comments(page.read_text(encoding="utf-8"))
    hrefs = re.findall(r'<a\s[^>]*href="([^"]+)"', html)
    local = [h for h in hrefs if not re.match(r"(https?:|mailto:|tel:)", h)]
    bad = []
    for h in local:
        if h == "#":
            bad.append("href='#'")
            continue
        target, frag = resolve(page, h)
        if not target.exists():
            bad.append(f"{h} -> missing {rel(target) if target.is_relative_to(ROOT) else target}")
        elif frag and frag not in ids_of(target):
            bad.append(f"{h} -> no id '{frag}' in {rel(target)}")
    for m in re.finditer(r'<a\s([^>]*target="_blank"[^>]*)>', html):
        if "noopener" not in m.group(1):
            bad.append(f"target=_blank without rel=noopener: {m.group(1)[:60]}")
    for ref in re.findall(r'\s(?:src|href)="((?!https?:|#|mailto:|data:)[^"]+)"', html):
        target, _ = resolve(page, ref)
        if not target.exists():
            bad.append(f"asset {ref} missing")
    ext = len(set(h for h in hrefs if h.startswith("http")))
    print(f"  {'ok  ' if not bad else 'FAIL'} {rel(page):36s} {len(local):3d} local links, {ext:2d} external")
    for b in sorted(set(bad)):
        fail(f"{rel(page)}: {b}")


# ── contrast ─────────────────────────────────────────────────────────────────
def lum(hexcol):
    c = hexcol.lstrip("#")
    rgb = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def ratio(a, b, dim=1.0):
    """Contrast of a on b; dim scales both luminances (a CSS brightness() filter)."""
    la, lb = lum(a) * dim, lum(b) * dim
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# The two palettes, read from the stylesheet itself so this list cannot drift from it.
css = (ROOT / "work" / "portfolio" / "site" / "styles.css").read_text(encoding="utf-8")
light = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-f]{6})", css.split("@media (prefers-color-scheme: dark)")[0]))
dark_block = re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\}', css, re.S).group(1)
dark = dict(light, **dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-f]{6})", dark_block)))

TEXT = [("ink", "body text"), ("ink-2", "secondary text"), ("muted", "muted text"), ("accent", "link / accent")]
GROUNDS = ["bg", "surface", "surface-2"]
print("\ncontrast (WCAG AA: 4.5:1 for body text):")
for theme, pal in [("light", light), ("dark", dark)]:
    rows = [(f"{name} on {g}", pal[fg], pal[g]) for fg, name in TEXT for g in GROUNDS]
    rows += [("button label", pal["btn-fg"], pal["btn-bg"]),
             ("button hover", pal["bg"], pal["accent"]),
             ("error text", pal["err"], pal["surface"]),
             ("success text", pal["ok"], pal["bg"])]
    for name, fg, bg in rows:
        r = ratio(fg, bg)
        good = r >= 4.5
        print(f"  {'ok  ' if good else 'FAIL'} {theme:5s} {name:28s} {r:5.2f}:1")
        if not good:
            fail(f"CONTRAST ({theme}): {name} is {r:.2f}:1")

# Text drawn inside the data figures sits on a white plate in both themes; in dark
# mode the plate is dimmed by brightness(.9), which scales luminance by 0.9.
figs = (ROOT / "work" / "scripts" / "make_project_figures.py").read_text(encoding="utf-8")
named = dict(zip(["INK", "NAVY", "SLATE", "MUTED", "GRID", "PAPER"],
                 re.search(r'INK, NAVY, SLATE, MUTED, GRID, PAPER = (.*)', figs).group(1).replace('"', "").split(", ")))
for label, col in [("figure ink", named["INK"]), ("figure navy", named["NAVY"]),
                   ("figure slate labels", named["SLATE"]), ("figure muted", named["MUTED"])]:
    for theme, dim in [("light", 1.0), ("dark", 0.9)]:
        r = ratio(col, named["PAPER"], dim)
        good = r >= 4.5
        print(f"  {'ok  ' if good else 'FAIL'} {theme:5s} {label:28s} {r:5.2f}:1")
        if not good:
            fail(f"CONTRAST ({theme}): {label} {col} on the figure plate is {r:.2f}:1")
for col in sorted(set(re.findall(r'fill="(#[0-9a-fA-F]{6})"', figs))):
    if col.lower() not in {named["PAPER"].lower()} and ratio(col, named["PAPER"]) < 4.5:
        fail(f"CONTRAST: a figure draws text or marks in {col}, {ratio(col, named['PAPER']):.2f}:1 on white")


# ── SEO, page by page ────────────────────────────────────────────────────────
def meta(html, attr, val):
    m = re.search(rf'<meta\s+{attr}="{re.escape(val)}"\s+content="([^"]*)"', html)
    return m.group(1) if m else None


print("\nSEO / meta:")
titles = {}
for page in PAGES:
    html = page.read_text(encoding="utf-8")
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    title = t.group(1).strip() if t else ""
    desc = meta(html, "name", "description") or ""
    titles[rel(page)] = title
    checks = [
        ("title 1-60 chars", 0 < len(title) <= 60),
        ("description 50-160 chars", 50 <= len(desc) <= 160),
        ("canonical URL", 'rel="canonical"' in html),
        ("robots directive", bool(meta(html, "name", "robots"))),
        ("og:title", bool(meta(html, "property", "og:title"))),
        ("og:description", bool(meta(html, "property", "og:description"))),
        ("og:url", bool(meta(html, "property", "og:url"))),
        ("og:image absolute", (meta(html, "property", "og:image") or "").startswith("https://")),
        ("og:image:alt", bool(meta(html, "property", "og:image:alt"))),
        ("twitter:card", meta(html, "name", "twitter:card") == "summary_large_image"),
        ("favicon", 'rel="icon"' in html),
        ("lang", "<html lang=" in html),
        ("viewport", 'name="viewport"' in html),
        ("exactly one <h1>", len(re.findall(r"<h1[\s>]", html)) == 1),
        ("skip link", 'class="skip"' in html),
    ]
    if page == SITE / "index.html":
        ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        try:
            json.loads(ld.group(1)) if ld else None
            checks.append(("JSON-LD parses", bool(ld)))
        except ValueError as e:
            checks.append((f"JSON-LD parses ({e})", False))
    failed = [n for n, good in checks if not good]
    print(f"  {'ok  ' if not failed else 'FAIL'} {rel(page):36s} title {len(title):2d} chars, description {len(desc):3d}"
          + (f"  — {', '.join(failed)}" if failed else ""))
    for n in failed:
        fail(f"SEO {rel(page)}: {n}")
dupes = {t for t in titles.values() if list(titles.values()).count(t) > 1}
if dupes:
    fail(f"SEO: pages share a title: {sorted(dupes)}")


# ── share image ──────────────────────────────────────────────────────────────
print("\nassets:")
og = SITE / "og.png"
if og.exists():
    raw = og.read_bytes()
    w, h = struct.unpack(">II", raw[16:24])
    good = (w, h) == (1200, 630)
    print(f"  {'ok  ' if good else 'FAIL'} og.png is {w}x{h} (want 1200x630), {len(raw) / 1024:.0f} KB")
    if not good:
        fail("ASSET: og.png wrong dimensions")
else:
    fail("ASSET: og.png missing")

print("\n" + "=" * 50)
if issues:
    print(f"{len(issues)} ISSUE(S):")
    for i in issues:
        print("  -", i)
    sys.exit(1)
print(f"NO ISSUES FOUND across {len(PAGES)} pages")
