#!/usr/bin/env python3
"""Week 9 launch audit — checks what "live on a real address" actually requires.

Covers both pages: the paper (docs/index.html, served from this repo) and the
portfolio (docs/portfolio/index.html, canonical at site.json's portfolio_url and
published there by export_user_site.py). Everything here is checkable offline,
from the files that GitHub Pages will serve. The three things it CANNOT check from here
are called out at the end, because they need the live URL.

    python3 work/scripts/audit_launch.py
"""
import json
import pathlib
import re
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from configure_site import analytics_from  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
CONFIG = ROOT / "work" / "portfolio" / "site.json"
PLACEHOLDER = "#badge-not-configured"

issues, warnings = [], []


def fail(msg):
    issues.append(msg)


def warn(msg):
    warnings.append(msg)


def check(label, ok, detail="", soft=False):
    print(f"  {'ok  ' if ok else ('warn' if soft else 'FAIL')} {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        (warn if soft else fail)(f"{label}{(' — ' + detail) if detail else ''}")
    return ok


def meta(html, attr, val):
    m = re.search(rf'<meta\s+{attr}="{re.escape(val)}"\s+content="([^"]*)"', html)
    return m.group(1) if m else None


def png_size(path):
    raw = path.read_bytes()
    return struct.unpack(">II", raw[16:24]) if raw[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)


cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
BASE = cfg["base_url"].rstrip("/")
# Sites this one links to deliberately (a sibling project on its own Pages
# address, say). Without this every intentional outbound link reads as a
# leftover of the previous address.
EXTERNAL = tuple(u.rstrip("/") for u in cfg.get("external_sites", []))
# The portfolio has its own root address (a user site), so its canonical URL no
# longer sits under BASE.
PORTFOLIO = cfg.get("portfolio_url") or f"{BASE}/portfolio/"
VERIFY = cfg.get("badge_verify_url", "")

# Read the counter the same way configure_site.py does, older keys included. A config
# that names two counters is a finding here, not a crash.
try:
    PROVIDER, ANALYTICS_ID = analytics_from(cfg)
    CONFIG_ERROR = ""
except SystemExit as e:
    PROVIDER, ANALYTICS_ID, CONFIG_ERROR = "", "", str(e).splitlines()[0]

# What a correctly stamped page looks like for each counter, and where its numbers show up.
ANALYTICS = {
    "ga4": (re.compile(r'gtag/js\?id=(G-[A-Z0-9]+)'), "Google Analytics"),
    "goatcounter": (re.compile(r'data-goatcounter="https://([a-z0-9-]+)\.goatcounter\.com/count"'),
                    "GoatCounter"),
}
DASHBOARD = ANALYTICS.get(PROVIDER, (None, "analytics"))[1]

print(f"base URL   {BASE}")
print(f"analytics  {f'{PROVIDER} {ANALYTICS_ID}' if PROVIDER else (CONFIG_ERROR or '(unset)')}")
print(f"badge link {VERIFY or '(unset)'}")

PAGES = [("paper", DOCS / "index.html", f"{BASE}/"),
         ("portfolio", DOCS / "portfolio" / "index.html", PORTFOLIO)]

titles = {}

for name, path, url in PAGES:
    print(f"\n=== {name}  ({path.relative_to(ROOT)}) ===")
    html = path.read_text(encoding="utf-8")
    here = path.parent

    def asset(ref):
        """Resolve a relative asset reference to a file on disk."""
        return (here / ref).resolve()

    # --- titles ---
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    title = t.group(1).strip() if t else ""
    titles[name] = title
    check("title present", bool(title), repr(title))
    check("title <= 60 chars", 0 < len(title) <= 60, f"{len(title)} chars")
    desc = meta(html, "name", "description") or ""
    check("description 50-160 chars", 50 <= len(desc) <= 160, f"{len(desc)} chars")

    # --- the real address ---
    canon = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    canon = canon.group(1) if canon else ""
    check("canonical points at the live URL", canon == url, canon or "missing")
    check("og:url matches canonical", meta(html, "property", "og:url") == url,
          meta(html, "property", "og:url") or "missing")

    # --- share preview ---
    # The share image is published next to the page, so it must sit under the
    # page's own address and exist in the page's own folder.
    ogimg = meta(html, "property", "og:image") or ""
    check("og:image is absolute", ogimg.startswith(url), ogimg or "missing")
    if ogimg.startswith(url):
        f = here / ogimg[len(url):]
        if check("og:image file exists", f.exists(), str(f.relative_to(ROOT)) if f.exists() else ogimg):
            w, h = png_size(f)
            check("og:image is 1200x630", (w, h) == (1200, 630), f"{w}x{h}, {f.stat().st_size/1024:.0f} KB")
    check("og:image:alt present", bool(meta(html, "property", "og:image:alt")))
    check("og:site_name present", bool(meta(html, "property", "og:site_name")))
    check("twitter:card is summary_large_image",
          meta(html, "name", "twitter:card") == "summary_large_image")
    check("twitter:image present", bool(meta(html, "name", "twitter:image")))

    # --- favicon ---
    ico = re.search(r'<link rel="icon" href="([^"]+)"', html)
    if check("favicon linked", bool(ico)):
        f = asset(ico.group(1))
        check("favicon file exists", f.exists(), ico.group(1))

    # --- basics ---
    check("lang attribute", "<html lang=" in html)
    check("viewport meta", 'name="viewport"' in html)
    check("exactly one <h1>", len(re.findall(r"<h1[\s>]", html)) == 1)
    check("theme-color set", bool(meta(html, "name", "theme-color")))

    # --- analytics ---
    # The block is generated (configure_site.py for the portfolio, build_paper.py for
    # the paper), so the page and site.json cannot drift apart: a page shipping a
    # counter site.json does not know about, or two counters at once, is a finding.
    block = re.search(r"<!-- analytics:start.*?<!-- analytics:end -->", html, re.S)
    if check("analytics block present", bool(block),
             "" if block else "no analytics:start/end markers — run configure_site.py"):
        body = block.group(0)
        check("analytics provider configured", bool(PROVIDER),
              f"{PROVIDER} {ANALYTICS_ID}" if PROVIDER else (CONFIG_ERROR or "unset — nothing will be counted"))
        found = [n for n, (pat, _) in ANALYTICS.items() if pat.search(body)]
        if PROVIDER:
            m = ANALYTICS[PROVIDER][0].search(body)
            check(f"{PROVIDER} snippet stamped into the page", bool(m),
                  m.group(0) if m else f"site.json says {PROVIDER} but the page has no such tag")
            if m:
                check("the stamped ID matches site.json", m.group(1) == ANALYTICS_ID,
                      f"page has {m.group(1)}, site.json has {ANALYTICS_ID}")
        check("exactly one analytics provider on the page", len(found) <= 1,
              " + ".join(found) if len(found) > 1 else "")
        # A counter outside the managed block would survive every regeneration.
        outside = html.replace(body, "")
        strays = [n for n, (pat, _) in ANALYTICS.items() if pat.search(outside)]
        strays += ["dead goatcounter stub"] if 'data-goatcounter=""' in outside else []
        check("no analytics outside the managed block", not strays, ", ".join(strays))

    # --- graduate badge ---
    b = re.search(r'<a class="grad-badge"[^>]*href="([^"]+)"[^>]*>\s*<img src="([^"]+)"[^>]*alt="([^"]*)"',
                  html, re.S)
    if check("graduate badge in footer", bool(b)):
        href, src, alt = b.group(1), b.group(2), b.group(3)
        in_footer = html.rindex('class="grad-badge"') > html.rindex("<footer")
        check("badge sits inside <footer>", in_footer)
        check("badge image file exists", asset(src).exists(), src)
        check("badge has alt text", len(alt) > 10)
        check("badge links to a verification page",
              href.startswith("https://") and href != PLACEHOLDER,
              "not set yet — run configure_site.py --verify <url>" if href == PLACEHOLDER else href)

# --- site-wide ---
print("\n=== site ===")
check("the two pages have different titles", titles.get("paper") != titles.get("portfolio"))

stray = set()
for f in list(DOCS.rglob("*.html")) + list(DOCS.rglob("*.xml")):
    for m in re.finditer(r'https://[a-z0-9.-]*(?:github\.io|is-a\.dev)[^\s"\'<>]*', f.read_text(encoding="utf-8")):
        url = m.group(0)
        # A file at the portfolio's root (the page itself, its share image) is
        # expected; a deeper path under that host is a project site and has to be
        # listed in external_sites like any other.
        at_portfolio = url.startswith(PORTFOLIO) and "/" not in url[len(PORTFOLIO):]
        if not url.startswith(BASE) and not url.startswith(EXTERNAL) and not at_portfolio:
            stray.add(url)
check("no URLs left pointing at the old address", not stray, "; ".join(sorted(stray)[:3]))

sitemap = DOCS / "sitemap.xml"
if sitemap.exists():
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap.read_text(encoding="utf-8"))
    check("sitemap URLs all use the live base", all(l.startswith(BASE) for l in locs),
          f"{len(locs)} URLs")
    check("sitemap lists the paper", f"{BASE}/" in locs)
    # The portfolio's own site carries its sitemap (export_user_site.py); listing
    # it here as well would advertise a URL this repo does not canonically serve.
    check("sitemap leaves the portfolio to its own site", PORTFOLIO not in locs)

cname = DOCS / "CNAME"
host = BASE.split("://", 1)[1].split("/", 1)[0]
if host.endswith("github.io"):
    check("CNAME absent (still on github.io)", not cname.exists(), soft=True,
          detail="no custom domain configured yet")
else:
    if check("CNAME present for the custom domain", cname.exists()):
        check("CNAME matches the canonical host", cname.read_text().strip() == host,
              cname.read_text().strip())

# --- nothing private in what gets served ---
leaked = []
for f in DOCS.rglob("*"):
    if f.is_file() and f.suffix in {".html", ".xml", ".md", ".txt", ".json", ".svg"}:
        body = f.read_text(encoding="utf-8", errors="ignore")
        for pat, label in [(r"\bAIza[0-9A-Za-z_-]{30,}", "Google API key"),
                           (r"\bghp_[0-9A-Za-z]{30,}", "GitHub token"),
                           (r"\bsk-[0-9A-Za-z]{30,}", "secret key")]:
            if re.search(pat, body):
                leaked.append(f"{f.relative_to(ROOT)}: {label}")
check("no obvious secrets in the served folder", not leaked, "; ".join(leaked))

print("\n" + "=" * 62)
print("Cannot be checked from here — do these on the live URL:")
print("  1. Open the address in a private window on desktop, then on your phone.")
print("  2. Paste the address into a share-preview debugger and confirm the card.")
print(f"  3. Reload twice and confirm the hit shows in the {DASHBOARD} dashboard.")
print("=" * 62)

if warnings:
    print(f"\n{len(warnings)} WARNING(S):")
    for w in warnings:
        print("  -", w)
if issues:
    print(f"\n{len(issues)} ISSUE(S):")
    for i in issues:
        print("  -", i)
    sys.exit(1)
print("\nNO BLOCKING ISSUES")
