import pathlib, re, sys

html = pathlib.Path("docs/portfolio/index.html").read_text(encoding="utf-8")
issues = []

# --- links ---
anchors = re.findall(r'<a\s[^>]*href="([^"]+)"[^>]*>', html)
ids = set(re.findall(r'\sid="([^"]+)"', html))
for h in anchors:
    if h == "#":
        issues.append(f"DEAD LINK: href='#'")
    elif h == "#badge-not-configured":
        # the graduate badge's placeholder; audit_launch.py owns this check
        issues.append("BADGE: verify URL not set — run configure_site.py --verify <url>")
    elif h.startswith("#") and h[1:] not in ids:
        issues.append(f"BROKEN ANCHOR: {h} has no matching id")
print(f"links: {len(anchors)} total, {len(set(a for a in anchors if a.startswith('http')))} external")

# external links must be safe
for m in re.finditer(r'<a\s([^>]*target="_blank"[^>]*)>', html):
    if "rel=" not in m.group(1) or "noopener" not in m.group(1):
        issues.append(f"target=_blank without rel=noopener: {m.group(1)[:70]}")

# --- images ---
imgs = re.findall(r'<img\s', html)
print(f"images: {len(imgs)} (none = nothing to break, nothing slow to load)")

# --- external requests ---
ext = set(re.findall(r'https://([a-z0-9.-]+)/', html))
print("external hosts:", ", ".join(sorted(ext)))

# --- contrast ---
def lum(hexcol):
    c = hexcol.lstrip("#")
    rgb = [int(c[i:i+2], 16)/255 for i in (0, 2, 4)]
    rgb = [v/12.92 if v <= 0.03928 else ((v+0.055)/1.055)**2.4 for v in rgb]
    return 0.2126*rgb[0] + 0.7152*rgb[1] + 0.0722*rgb[2]

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

# Every text colour the page sets, on every ground it sits on. The ghost numerals
# (#cfccc4) and the slate squares are aria-hidden decoration and carry no meaning,
# so they are deliberately not in this list.
pairs = [
    ("body text",          "#111111", "#ffffff", 4.5),
    ("body on paper-2",    "#111111", "#f4f3ef", 4.5),
    ("secondary text",     "#3d4247", "#ffffff", 4.5),
    ("secondary on p-2",   "#3d4247", "#f4f3ef", 4.5),
    ("muted text",         "#5f6469", "#ffffff", 4.5),
    ("muted on paper-2",   "#5f6469", "#f4f3ef", 4.5),
    ("navy link",          "#1c2d3d", "#ffffff", 4.5),
    ("white on navy",      "#ffffff", "#1c2d3d", 4.5),
    ("soft on navy",       "#c3ccd5", "#1c2d3d", 4.5),
    ("soft on navy hover", "#c3ccd5", "#243a4e", 4.5),
    ("white on ink",       "#ffffff", "#111111", 4.5),
    ("footer text",        "#a3a8ad", "#0e0e0e", 4.5),
    ("error text",         "#b91c1c", "#ffffff", 4.5),
    ("setup note",         "#92400e", "#fffbeb", 4.5),
    ("success status",     "#15803d", "#ffffff", 4.5),
]
print("\ncontrast (WCAG AA needs 4.5:1 for body text):")
for name, fg, bg, need in pairs:
    r = ratio(fg, bg)
    ok = r >= need
    print(f"  {'ok  ' if ok else 'FAIL'} {name:18s} {r:5.2f}:1")
    if not ok:
        issues.append(f"CONTRAST: {name} is {r:.2f}:1, needs {need}:1")

# --- SEO / meta ---
import json as _json, struct as _struct
print("\nSEO / meta:")

def meta(attr, val):
    m = re.search(rf'<meta\s+{attr}="{re.escape(val)}"\s+content="([^"]*)"', html)
    return m.group(1) if m else None

title = re.search(r"<title>(.*?)</title>", html, re.S)
title = title.group(1).strip() if title else ""
desc = meta("name", "description") or ""

checks = [
    ("<title> present",        bool(title)),
    ("title <= 60 chars",      0 < len(title) <= 60),
    ("description present",    bool(desc)),
    ("description 50-160",     50 <= len(desc) <= 160),
    ("canonical URL",          'rel="canonical"' in html),
    ("robots directive",       bool(meta("name", "robots"))),
    ("og:title",               bool(meta("property", "og:title"))),
    ("og:description",         bool(meta("property", "og:description"))),
    ("og:url",                 bool(meta("property", "og:url"))),
    ("og:image (absolute)",    (meta("property", "og:image") or "").startswith("https://")),
    ("og:image:alt",           bool(meta("property", "og:image:alt"))),
    ("twitter:card",           meta("name", "twitter:card") == "summary_large_image"),
    ("favicon linked",         'rel="icon"' in html),
    ("lang attribute",         '<html lang=' in html),
    ("viewport meta",          'name="viewport"' in html),
    ("exactly one <h1>",       len(re.findall(r"<h1[\s>]", html)) == 1),
]

ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
if ld:
    try:
        _json.loads(ld.group(1))
        checks.append(("JSON-LD parses", True))
    except Exception as e:
        checks.append((f"JSON-LD parses ({e})", False))
else:
    checks.append(("JSON-LD present", False))

for name, good in checks:
    print(f"  {'ok  ' if good else 'FAIL'} {name}")
    if not good:
        issues.append(f"SEO: {name}")

print(f"  info title is {len(title)} chars, description {len(desc)} chars")

# --- assets referenced by the page must exist, at the right size ---
print("\nassets:")
base = pathlib.Path("docs/portfolio")
for f in ["favicon.svg", "og.png"]:
    exists = (base / f).exists()
    print(f"  {'ok  ' if exists else 'FAIL'} {f} present")
    if not exists:
        issues.append(f"ASSET: {f} missing")

og = base / "og.png"
if og.exists():
    raw = og.read_bytes()
    w, h = _struct.unpack(">II", raw[16:24])          # PNG IHDR
    good = (w, h) == (1200, 630)
    print(f"  {'ok  ' if good else 'FAIL'} og.png is {w}x{h} (want 1200x630), {len(raw)/1024:.0f} KB")
    if not good:
        issues.append("ASSET: og.png wrong dimensions")

print("\n" + ("=" * 50))
if issues:
    print(f"{len(issues)} ISSUE(S):")
    for i in issues:
        print("  -", i)
    sys.exit(1)
print("NO ISSUES FOUND")
