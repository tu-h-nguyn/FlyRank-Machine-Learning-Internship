#!/usr/bin/env python3
"""Week 9 launch audit — checks what "live on a real address" actually requires.

Covers both served pages: the paper (docs/index.html) and the portfolio
(docs/portfolio/index.html). Everything here is checkable offline, from the
files that GitHub Pages will serve. The three things it CANNOT check from here
are called out at the end, because they need the live URL.

    python3 work/scripts/audit_launch.py
"""
import json
import pathlib
import re
import struct
import sys

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
CODE = cfg.get("goatcounter_code", "")
VERIFY = cfg.get("badge_verify_url", "")

print(f"base URL   {BASE}")
print(f"analytics  {CODE or '(unset)'}")
print(f"badge link {VERIFY or '(unset)'}")

PAGES = [("paper", DOCS / "index.html", f"{BASE}/"),
         ("portfolio", DOCS / "portfolio" / "index.html", f"{BASE}/portfolio/")]

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
    ogimg = meta(html, "property", "og:image") or ""
    check("og:image is absolute", ogimg.startswith(BASE + "/"), ogimg or "missing")
    if ogimg.startswith(BASE + "/"):
        f = DOCS / ogimg[len(BASE) + 1:]
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
    # Two snippets can carry it: GoatCounter (data-goatcounter) and GA4
    # (gtag config). Either one counted is enough — the site currently runs
    # GA4 with GoatCounter left unset, and flagging that forever is noise.
    tag = re.search(r'data-goatcounter="([^"]*)"', html)
    ga4 = re.search(r"gtag\('config',\s*'(G-[A-Z0-9]+)'\)", html)
    if check("analytics snippet present", bool(tag) or bool(ga4)):
        endpoint = tag.group(1) if tag else ""
        measured = endpoint or (ga4.group(1) if ga4 else "")
        check("analytics code configured", bool(measured),
              measured or "empty — nothing will be counted")
        if endpoint:
            check("analytics endpoint well formed",
                  re.fullmatch(r"https://[a-z0-9-]+\.goatcounter\.com/count", endpoint) is not None,
                  endpoint)

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
        if not url.startswith(BASE) and not url.startswith(EXTERNAL):
            stray.add(url)
check("no URLs left pointing at the old address", not stray, "; ".join(sorted(stray)[:3]))

sitemap = DOCS / "sitemap.xml"
if sitemap.exists():
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap.read_text(encoding="utf-8"))
    check("sitemap URLs all use the live base", all(l.startswith(BASE) for l in locs),
          f"{len(locs)} URLs")
    check("sitemap lists both pages", {f"{BASE}/", f"{BASE}/portfolio/"} <= set(locs))

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
print("  3. Reload twice and confirm the hit shows in the GoatCounter dashboard.")
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
