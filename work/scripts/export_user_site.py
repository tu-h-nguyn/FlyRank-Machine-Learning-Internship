#!/usr/bin/env python3
"""Build the portfolio's own site — https://tu-h-nguyn.github.io/ — from docs/portfolio/.

The portfolio is written and tested here, in docs/portfolio/, where the browser
suites and audits already point. What GitHub serves at the bare user address is
a separate repository, `tu-h-nguyn/tu-h-nguyn.github.io`, and this script is the
only thing that writes into it: that repository is build output, so it can never
drift from the page the tests ran against.

What changes on the way out:
  * any ../assets/ reference moves to assets/, since the site is now its own root
  * robots.txt, sitemap.xml, a 404 page and .nojekyll are added — all of which
    only work at a domain root, which is exactly what a project page could not have

    python3 work/scripts/export_user_site.py                  # -> build/user-site/
    python3 work/scripts/export_user_site.py --out /some/dir

Publishing is .github/workflows/deploy-user-site.yml, on every push to main that
touches the portfolio. Run by hand, this only builds; it never pushes.
"""
import argparse
import datetime
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "portfolio"
BADGE = ROOT / "docs" / "assets" / "flyrank-graduate-badge.svg"
CONFIG = ROOT / "work" / "portfolio" / "site.json"
UPSTREAM = "https://github.com/tu-h-nguyn/FlyRank-Machine-Learning-Internship"


def page_404(portfolio, paper):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Not found — Nguyễn Hoàng Tú</title>
  <meta name="robots" content="noindex">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{min-height:100vh;display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);
         font-family:Georgia,'Times New Roman',serif;color:#111;background:#fff}}
    .panel{{background:#1c2d3d;color:#fff;display:flex;align-items:flex-end;padding:3rem}}
    .panel span{{font-size:clamp(96px,16vw,13rem);font-weight:900;line-height:.8;font-style:italic}}
    main{{display:flex;flex-direction:column;justify-content:center;padding:3rem clamp(1.5rem,6vw,5rem)}}
    h1{{font-size:clamp(32px,4.4vw,3.6rem);line-height:1.1;font-weight:900}}
    p{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#3d4247;margin-top:1.2rem;max-width:30rem;line-height:1.7}}
    nav{{display:flex;flex-wrap:wrap;gap:.75rem;margin-top:2rem}}
    a{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:.8rem;letter-spacing:.14em;
       text-transform:uppercase;text-decoration:none;color:#111;border:1px solid #111;padding:.9rem 1.4rem}}
    a:first-child{{background:#111;color:#fff}}
    @media (max-width:700px){{body{{grid-template-columns:minmax(0,1fr)}}.panel{{padding:2rem 1.5rem}}}}
  </style>
</head>
<body>
  <div class="panel" aria-hidden="true"><span>404</span></div>
  <main>
    <h1>This page is not here.</h1>
    <p>The address may be mistyped, or the page may have moved. Everything that is here starts from the portfolio.</p>
    <nav>
      <a href="{portfolio}">Portfolio</a>
      <a href="{paper}">Research paper</a>
    </nav>
  </main>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "user-site"))
    args = ap.parse_args()
    out = pathlib.Path(args.out).resolve()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    portfolio = cfg["portfolio_url"]
    paper = cfg["base_url"].rstrip("/") + "/"
    if not re.fullmatch(r"https://[a-z0-9-]+\.github\.io/", portfolio):
        sys.exit(f"portfolio_url must be a bare user site like https://name.github.io/ — got {portfolio!r}")

    html = (SRC / "index.html").read_text(encoding="utf-8")

    # The page must already say it lives at the new address; this script moves
    # files, it does not decide where the canonical copy is.
    canon = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    if not canon or canon.group(1) != portfolio:
        sys.exit(f"docs/portfolio/index.html canonical is {canon and canon.group(1)!r}, "
                 f"expected {portfolio!r} (site.json portfolio_url)")

    # Shared assets live one level up in this repo; at the user site they sit at the root.
    uses_badge = 'src="../assets/' in html
    html = html.replace('src="../assets/', 'src="assets/')

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    (out / "index.html").write_text(html, encoding="utf-8")
    for name in ["favicon.svg", "og.png"]:
        shutil.copy2(SRC / name, out / name)
    shutil.copytree(SRC / "figures", out / "figures")
    if uses_badge:
        (out / "assets").mkdir()
        shutil.copy2(BADGE, out / "assets" / BADGE.name)

    today = datetime.date.today().isoformat()
    (out / "robots.txt").write_text(
        # This file governs every project site under the same host too, so it
        # allows everything and only points crawlers at the sitemap.
        f"User-agent: *\nAllow: /\n\nSitemap: {portfolio}sitemap.xml\n", encoding="utf-8")
    (out / "sitemap.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{portfolio}</loc>
    <lastmod>{today}</lastmod>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{paper}</loc>
    <lastmod>{today}</lastmod>
    <priority>0.8</priority>
  </url>
</urlset>
""", encoding="utf-8")
    (out / "404.html").write_text(page_404(portfolio, paper), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "README.md").write_text(f"""# {portfolio.split('//')[1].rstrip('/')}

Portfolio of Nguyễn Hoàng Tú — live at **{portfolio}**

**Do not edit this repository by hand.** Every file here is generated from
[`docs/portfolio/`]({UPSTREAM}/tree/main/docs/portfolio) in
[{UPSTREAM.split('github.com/')[1]}]({UPSTREAM}) by
`work/scripts/export_user_site.py`, and replaced wholesale on each publish. Edit the
page there, where the browser tests and audits run, and push to `main`.
""", encoding="utf-8")

    # Every local file the page points at has to have made it across. Comments are
    # skipped: the portrait instructions name a portrait.jpg that does not exist yet.
    live = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    missing = [ref for ref in re.findall(r'(?:src|href)="((?!https?:|#|mailto:)[^"]+)"', live)
               if not (out / ref).exists()]
    if missing:
        sys.exit(f"exported page references missing files: {missing}")

    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    size = sum((out / f).stat().st_size for f in files)
    print(f"built {out}  ({len(files)} files, {size / 1024:.0f} KB) for {portfolio}")
    for f in files:
        print("  ", f)


if __name__ == "__main__":
    main()
