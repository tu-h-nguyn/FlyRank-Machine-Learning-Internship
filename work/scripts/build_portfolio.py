#!/usr/bin/env python3
"""Build the portfolio — every page of it — from work/portfolio/site/ into docs/portfolio/.

The site is plain static HTML with no framework. What a framework would give — one
header, one footer, one stylesheet shared by every page — this script gives by
assembly, with no dependency beyond the standard library:

    work/portfolio/site/layout.html     head, nav, footer; {{tokens}} filled per page
    work/portfolio/site/styles.css      the one stylesheet  } inlined into every page,
    work/portfolio/site/site.js         the one script      } so each is one request
    work/portfolio/site/pages/*.html    page bodies, each opening with a JSON header

    docs/portfolio/index.html, projects/, thesis/, cv/     the built pages (served)

A page body can use {{root}} (relative path to the site root, so links work at
tu-h-nguyn.github.io/ and under this repo's /portfolio/ alike) and {{home_sections}}
(the home page, for its #anchors). The analytics block comes from site.json through
the same function configure_site.py uses. Figures between figure:NAME markers are
written into the page sources by make_project_figures.py before this runs.

    python3 work/scripts/build_portfolio.py            # build
    python3 work/scripts/build_portfolio.py --check    # fail if docs/portfolio is stale
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from configure_site import analytics_block, analytics_from  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "portfolio" / "site"
OUT = ROOT / "docs" / "portfolio"
CONFIG = ROOT / "work" / "portfolio" / "site.json"

HEADER = re.compile(r"\A<!--page\s*(\{.*?\})\s*-->\n", re.S)

NAV = [("Projects", "projects"), ("Research", "research"), ("Writing", "writing"),
       ("Skills", "skills"), ("About", "about")]

PERSON = {
    "@context": "https://schema.org",
    "@type": "Person",
    "name": "Nguyễn Hoàng Tú",
    "alternateName": "Tu Nguyen",
    "jobTitle": "Mathematics and Computer Science undergraduate",
    "affiliation": {"@type": "CollegeOrUniversity", "name": "VNU-HCM University of Science"},
    "knowsAbout": ["Numerical Analysis", "Finite Element Method", "Finite Volume Method",
                   "Linear Multistep Methods", "Convex Optimization", "Machine Learning",
                   "Physics-Informed Neural Networks", "Automatic Differentiation",
                   "Information Retrieval", "Quantitative Research", "Python", "PyTorch"],
    "sameAs": ["https://github.com/tu-h-nguyn", "https://www.linkedin.com/in/tuhcmus/"],
}


def indent(text, pad):
    return "\n".join(pad + ln if ln.strip() else "" for ln in text.rstrip("\n").split("\n"))


def load_pages():
    pages = []
    for f in sorted((SRC / "pages").glob("*.html")):
        raw = f.read_text(encoding="utf-8")
        m = HEADER.match(raw)
        if not m:
            sys.exit(f"{f.relative_to(ROOT)}: missing the <!--page {{...}} --> header")
        meta = json.loads(m.group(1))
        meta["body"] = raw[m.end():]
        meta["source"] = f
        pages.append(meta)
    return pages


def render(page, cfg, layout, css, js):
    path = page["path"]                                  # "" or "projects/"
    depth = path.count("/")
    root = "../" * depth
    home = root or "./"
    home_sections = root                                  # "" on the home page itself
    base = cfg["portfolio_url"]
    canonical = base + path

    def nav_href(anchor):
        return f"{home_sections}#{anchor}"

    links, menu = [], []
    for i, (label, anchor) in enumerate(NAV, 1):
        href = f"{root}projects/" if (anchor == "projects" and path) else nav_href(anchor)
        cur = ' aria-current="page"' if page.get("nav") == anchor else ""
        links.append(f'<a href="{href}"{cur}>{label}</a>')
        menu.append(f'<a href="{href}"><span>0{i}</span>{label}</a>')
    cur = ' aria-current="page"' if page.get("nav") == "cv" else ""
    links.append(f'<a class="cv" href="{root}cv/"{cur}>CV</a>')
    menu.append(f'<a href="{root}cv/"><span>0{len(NAV) + 1}</span>CV</a>')

    provider, ident = analytics_from(cfg)
    jsonld = ""
    if page.get("jsonld") == "person":
        person = dict(PERSON, url=base, image=base + "og.png")
        jsonld = ('  <script type="application/ld+json">\n'
                  + indent(json.dumps(person, ensure_ascii=False, indent=2), "  ")
                  + "\n  </script>")

    page_js = ""
    for name in page.get("page_js", []):
        page_js += (SRC / f"{name}.js").read_text(encoding="utf-8").rstrip("\n") + "\n"
    if page_js:
        page_js = "  <script>\n" + indent(page_js, "  ") + "\n  </script>"

    values = {
        "title": page["title"],
        "description": page["description"],
        "canonical": canonical,
        "og_type": page.get("og_type", "website"),
        "og_title": page.get("og_title", page["title"]),
        "og_description": page.get("og_description", page["description"]),
        "og_image": base + "og.png",
        "og_image_alt": page.get("og_image_alt", "Nguyễn Hoàng Tú, Mathematics × Computer Science: machine learning, numerical methods and quantitative research, with a world map magnifying Việt Nam."),
        "gsv": cfg.get("google_site_verification", ""),
        "analytics": analytics_block(provider, ident, "  "),
        "jsonld": jsonld,
        "css": indent(css, "    "),
        "js": indent(js, "  "),
        "nav_links": indent("\n".join(links), "          "),
        "menu_links": indent("\n".join(menu), "      "),
        "home": home,
        "home_sections": home_sections,
        "root": root,
        "page_js": page_js,
    }
    body = page["body"].replace("{{root}}", root).replace("{{home_sections}}", home_sections)
    values["body"] = body.rstrip("\n")

    out = layout
    # body last, so a {{token}} that happens to appear in page content is never re-filled
    for key, val in values.items():
        if key != "body":
            out = out.replace("{{" + key + "}}", val)
    out = out.replace("{{body}}", values["body"])
    left = re.findall(r"\{\{[a-z_]+\}\}", out)
    if left:
        sys.exit(f"{page['source'].name}: unfilled tokens {sorted(set(left))}")
    return OUT / path / "index.html", out


def build(check=False, quiet=False, cfg=None):
    """Render every page; write the stale ones unless check. Returns the stale paths.

    cfg defaults to site.json; configure_site.py passes the config it is about to save."""
    cfg = cfg or json.loads(CONFIG.read_text(encoding="utf-8"))
    layout = (SRC / "layout.html").read_text(encoding="utf-8")
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    js = (SRC / "site.js").read_text(encoding="utf-8")

    stale = []
    for page in load_pages():
        target, html = render(page, cfg, layout, css, js)
        rel = target.relative_to(ROOT)
        if target.exists() and target.read_text(encoding="utf-8") == html:
            if not quiet:
                print(f"  {rel}: current")
            continue
        stale.append(str(rel))
        if not check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
            print(f"  {rel}: built ({len(html.encode()) / 1024:.0f} KB)")
    return stale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if any built page is stale")
    args = ap.parse_args()
    stale = build(check=args.check)
    if args.check and stale:
        sys.exit("stale — run build_portfolio.py: " + ", ".join(stale))


if __name__ == "__main__":
    main()
