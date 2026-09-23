#!/usr/bin/env python3
"""Typeset the portfolio's formulas with KaTeX, at build time.

Every formula on the page is written in LaTeX, in a data-tex attribute:

    <span class="p-math" data-tex="M\\ddot u + c^2 K u = 0"><!--tex-->…<!--/tex--></span>   display
    <span class="tex-i"  data-tex="M^{-1}K"><!--tex-->…<!--/tex--></span>                    inline

and everything between <!--tex--> and <!--/tex--> is generated here: KaTeX's HTML
(which renders with the KaTeX fonts, like LaTeX) plus hidden MathML for screen
readers. No JavaScript runs in the browser; the page only loads KaTeX's stylesheet.

    (cd work/portfolio/math && npm install)       # once: KaTeX, pinned in package.json
    python3 work/scripts/render_math.py            # rewrite the typeset formulas
    python3 work/scripts/render_math.py --check    # fail if any is stale
"""
import argparse
import html
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "portfolio" / "index.html"
MATH = ROOT / "work" / "portfolio" / "math"
SPAN = re.compile(r'(<span class="(p-math|tex-i)" data-tex="([^"]*)">)<!--tex-->.*?<!--/tex-->(</span>)', re.S)


def render(items):
    if not (MATH / "node_modules" / "katex").exists():
        sys.exit("KaTeX is not installed — run: (cd work/portfolio/math && npm install)")
    out = subprocess.run(["node", str(MATH / "render.js")], input=json.dumps(items),
                         capture_output=True, text=True, check=False)
    if out.returncode:
        sys.exit("KaTeX failed:\n" + out.stderr)
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if any formula is stale")
    args = ap.parse_args()

    page = PAGE.read_text(encoding="utf-8")
    found = list(SPAN.finditer(page))
    items = [{"tex": html.unescape(m.group(3)), "display": m.group(2) == "p-math"} for m in found]
    typeset = render(items)
    new, last = [], 0
    for m, out in zip(found, typeset):
        new += [page[last:m.start()], m.group(1), "<!--tex-->", out, "<!--/tex-->", m.group(4)]
        last = m.end()
    new = "".join(new + [page[last:]])

    rel = PAGE.relative_to(ROOT)
    if new == page:
        print(f"{rel}: {len(found)} formulas current")
        return
    if args.check:
        sys.exit(f"{rel}: formulas are stale — run render_math.py")
    PAGE.write_text(new, encoding="utf-8")
    print(f"{rel}: {len(found)} formulas typeset")


if __name__ == "__main__":
    main()
