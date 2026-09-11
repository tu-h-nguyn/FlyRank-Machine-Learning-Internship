#!/usr/bin/env python3
"""Render docs/portfolio/og.png — the 1200x630 social-share card for the portfolio.

This card is what LinkedIn and Facebook show when the portfolio link is posted, so
it is the first thing most readers see. It used to be a hand-made file with no
source, which meant it silently went stale as the page changed. Now it is
generated, like the paper's card next to it.

    pip install playwright && python3 work/scripts/make_portfolio_og.py
"""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "portfolio" / "og.png"

CARD = """
<style>
  @page { margin:0 }
  *{box-sizing:border-box; margin:0}
  body{width:1200px; height:630px; background:#fafaf9; color:#18181b;
       font-family:"Liberation Sans","DejaVu Sans",system-ui,sans-serif;
       display:flex; flex-direction:column; justify-content:center;
       padding:0 78px; position:relative}
  .bar{position:absolute; left:0; top:0; bottom:0; width:14px; background:#0369a1}
  h1{font-size:74px; font-weight:700; letter-spacing:-.03em; line-height:1.05}
  .role{font-size:29px; font-weight:700; color:#0369a1; margin-top:14px;
        letter-spacing:-.01em}
  .deck{font-size:23px; color:#52525b; line-height:1.5; margin-top:26px; max-width:41ch}
  .rule{height:1px; background:#d4d4d8; margin:34px 0 26px}
  .stats{display:flex; gap:68px}
  .n{font-size:36px; font-weight:700; color:#0369a1; letter-spacing:-.02em}
  .l{font-size:17px; color:#52525b; margin-top:6px}
</style>
<div class="bar"></div>
<h1>Nguy&#7877;n Ho&agrave;ng T&uacute;</h1>
<p class="role">Machine Learning Engineer / AI Engineer Intern</p>
<p class="deck">ML systems end to end, and numerical solvers whose error is measured
   against an exact solution. Both come down to one habit: not trusting a number
   until something independent checks it.</p>
<div class="rule"></div>
<div class="stats">
  <div><div class="n">18,010</div><div class="l">pages ranked, out-of-fold</div></div>
  <div><div class="n">0.88</div><div class="l">precision@50 vs 0.74 baseline</div></div>
  <div><div class="n">6 public</div><div class="l">repositories; four verify results in CI</div></div>
</div>
"""


def chromium():
    for p in sorted(pathlib.Path("/opt/pw-browsers").glob("chromium*/chrome-linux/chrome")):
        return str(p)
    direct = pathlib.Path("/opt/pw-browsers/chromium")
    if direct.exists():
        return str(direct)
    return shutil.which("chromium") or shutil.which("google-chrome")


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed — pip install playwright")

    with sync_playwright() as pw:
        exe = chromium()
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630},
                                device_scale_factor=1)
        page.set_content(CARD, wait_until="load")
        page.screenshot(path=str(OUT))
        browser.close()

    print(f"{OUT.relative_to(ROOT)}  {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
