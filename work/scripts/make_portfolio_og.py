#!/usr/bin/env python3
"""Render docs/portfolio/og.png — the 1200x630 social-share card for the portfolio.

This card is what LinkedIn and Facebook show when the portfolio link is posted, so
it is the first thing most readers see. It used to be a hand-made file with no
source, which meant it silently went stale as the page changed. Now it is
generated, like the paper's card next to it, and drawn in the page's own system:
the navy panel with the "Who I am" box and the two squares, the name in Playfair
Display, the label type in Be Vietnam Pro.

The fonts are vendored in work/portfolio/fonts/ and embedded into the card, so it
renders the same with no network — and the script refuses to write the PNG if they
did not load, rather than quietly shipping a card set in a fallback face.

    pip install playwright && python3 work/scripts/make_portfolio_og.py
"""
import base64
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "portfolio" / "og.png"
FONTS = ROOT / "work" / "portfolio" / "fonts"

CARD = """
<style>
  {fonts}
  *{{box-sizing:border-box; margin:0; padding:0}}
  body{{width:1200px; height:630px; display:grid; grid-template-columns:430px 1fr;
       font-family:'Be Vietnam Pro', sans-serif; color:#111; background:#fff;
       -webkit-font-smoothing:antialiased}}

  .panel{{background:#1c2d3d; color:#fff; padding:62px 56px 54px;
         display:flex; flex-direction:column}}
  .who{{align-self:flex-start; border:3px solid #fff; padding:15px 30px 16px;
       font-weight:600; font-size:30px; letter-spacing:.14em; text-transform:uppercase;
       line-height:1.1}}
  .squares{{position:relative; width:190px; height:150px; margin-top:58px}}
  .squares i{{position:absolute; width:108px; height:108px; background:#6d8397}}
  .squares i:first-child{{left:0; top:42px; opacity:.5}}
  .squares i:last-child{{left:78px; top:0; opacity:.78}}
  .url{{margin-top:auto; font-size:18px; letter-spacing:.12em; color:#c3ccd5}}

  .main{{padding:60px 64px 54px 60px; display:flex; flex-direction:column}}
  .eyebrow{{display:flex; align-items:center; gap:16px; font-size:15px;
           letter-spacing:.24em; text-transform:uppercase; color:#5f6469}}
  .eyebrow::before, .eyebrow::after{{content:""; width:44px; height:1px; background:currentColor}}
  h1{{font-family:'Playfair Display', serif; font-weight:900; font-size:98px;
     line-height:.98; letter-spacing:-.015em; margin-top:24px}}
  .role{{align-self:flex-start; margin-top:30px; padding-bottom:12px;
        border-bottom:1px solid #111;
        font-family:'Playfair Display', serif; font-weight:400; font-size:19px;
        letter-spacing:.2em; text-transform:uppercase}}

  .stats{{margin-top:auto; display:grid; grid-template-columns:repeat(3, auto);
         justify-content:start; border-top:1px solid #e3e1dc; padding-top:24px}}
  .stat{{padding:0 30px; border-left:1px solid #e3e1dc}}
  .stat:first-child{{padding-left:0; border-left:0}}
  .n{{font-family:'Playfair Display', serif; font-weight:900; font-size:46px; line-height:1}}
  .l{{font-size:15px; line-height:1.4; color:#5f6469; margin-top:10px; max-width:180px}}
</style>
<div class="panel">
  <p class="who">Who I am</p>
  <div class="squares"><i></i><i></i></div>
  <p class="url">tu-h-nguyn.github.io</p>
</div>
<div class="main">
  <p class="eyebrow">Portfolio</p>
  <h1>Nguy&#7877;n<br>Ho&agrave;ng T&uacute;</h1>
  <p class="role">Machine Learning / AI Engineer</p>
  <div class="stats">
    <div class="stat"><div class="n">18,010</div><div class="l">pages ranked<br>out-of-fold</div></div>
    <div class="stat"><div class="n">0.88</div><div class="l">precision@50 vs a 0.74 baseline</div></div>
    <div class="stat"><div class="n">6</div><div class="l">public repositories, five verified in CI</div></div>
  </div>
</div>
"""


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
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed — pip install playwright")

    html = CARD.format(fonts=font_css())

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
            ["900 98px 'Playfair Display'", "Nguyễn Hoàng Tú 18,010 0.88"],
            ["400 19px 'Playfair Display'", "MACHINE LEARNING / AI ENGINEER"],
            ["400 15px 'Be Vietnam Pro'", "pages ranked out-of-fold tu-h-nguyn.github.io"],
            ["600 30px 'Be Vietnam Pro'", "WHO I AM"],
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
