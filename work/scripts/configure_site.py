#!/usr/bin/env python3
"""Apply work/portfolio/site.json to everything served out of docs/.

Three things live in one place and get stamped into the pages from here, so
going live on a new address is one command instead of a hunt through the HTML:

    base_url                        the address the site is canonical on
    analytics_provider/analytics_id which visitor counter loads, if any
    badge_verify_url                where the FlyRank graduate badge points

The analytics block is *generated*, not edited: everything between the
`analytics:start` and `analytics:end` comments in each page is rewritten from
the config. Exactly one counter can be configured, so the pages can never end
up shipping two of them — or a dead snippet that loads nothing.

Usage
    python3 work/scripts/configure_site.py                    # apply site.json as-is
    python3 work/scripts/configure_site.py --go-live          # switch to base_url_target
    python3 work/scripts/configure_site.py --base https://x.dev
    python3 work/scripts/configure_site.py --analytics G-ABC1234567   # GA4
    python3 work/scripts/configure_site.py --analytics hoangtu        # GoatCounter
    python3 work/scripts/configure_site.py --analytics none           # no counter at all
    python3 work/scripts/configure_site.py --verify https://.../verify/abc
    python3 work/scripts/configure_site.py --check            # report only, change nothing

Safe to run repeatedly: every rewrite is idempotent.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / "work" / "portfolio" / "site.json"
DOCS = ROOT / "docs"
CNAME = DOCS / "CNAME"

# Every file that may carry an absolute site URL.
TARGETS = ["index.html", "portfolio/index.html", "sitemap.xml"]

# A GA4 measurement ID; anything else is read as a GoatCounter site code.
GA4_ID = re.compile(r"G-[A-Z0-9]{6,12}")
GOATCOUNTER_CODE = re.compile(r"[a-z0-9][a-z0-9-]{1,48}")

BLOCK = re.compile(
    r"([ \t]*)<!-- analytics:start.*?-->.*?<!-- analytics:end -->",
    re.S,
)


def analytics_from(cfg):
    """(provider, id) from a site.json dict, including the two older per-counter keys.

    site.json used to carry `goatcounter_code` and `ga4_id` side by side, which let both
    be set at once. Either still reads; both set is refused rather than guessed at.
    """
    if cfg.get("analytics_id"):
        return read_analytics(cfg["analytics_id"])
    ga4, goat = cfg.get("ga4_id", ""), cfg.get("goatcounter_code", "")
    if ga4 and goat:
        sys.exit("site.json sets both ga4_id and goatcounter_code — pick one counter:\n"
                 "  python3 work/scripts/configure_site.py --analytics <G-XXXXXXX | goatcounter-code>")
    return read_analytics(ga4 or goat)


def load():
    """Read site.json, folding the older per-counter keys into analytics_provider/analytics_id."""
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["analytics_provider"], cfg["analytics_id"] = analytics_from(cfg)
    cfg.pop("ga4_id", None)
    cfg.pop("goatcounter_code", None)
    return cfg


def save(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_analytics(value):
    """Turn one --analytics argument into (provider, id). Empty/none means no counter."""
    value = (value or "").strip()
    if not value or value.lower() in {"none", "off"}:
        return "", ""
    if value.upper().startswith("G-"):
        if not GA4_ID.fullmatch(value.upper()):
            sys.exit(f"not a GA4 measurement ID: {value!r} (expected G- followed by 6-12 characters)")
        return "ga4", value.upper()
    if not GOATCOUNTER_CODE.fullmatch(value):
        sys.exit(f"not a GoatCounter site code: {value!r} (lowercase letters, digits and dashes)")
    return "goatcounter", value


def analytics_block(provider, ident, indent=""):
    """The exact HTML that belongs between the analytics markers."""
    if provider == "ga4":
        body = [
            "<!-- Google Analytics 4. Sets cookies: see work/portfolio/GO-LIVE.md on consent. -->",
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={ident}"></script>',
            "<script>",
            "  window.dataLayer = window.dataLayer || [];",
            "  function gtag(){dataLayer.push(arguments);}",
            "  gtag('js', new Date());",
            f"  gtag('config', '{ident}');",
            "</script>",
        ]
    elif provider == "goatcounter":
        body = [
            "<!-- GoatCounter: no cookies, no personal data, no consent banner required. -->",
            '<script async src="https://gc.zgo.at/count.js"'
            f' data-goatcounter="https://{ident}.goatcounter.com/count"></script>',
        ]
    else:
        body = [
            "<!-- No analytics configured, so no counter loads at all. Set one with:",
            "     python3 work/scripts/configure_site.py --analytics <G-XXXXXXX | goatcounter-code> -->",
        ]
    lines = ["<!-- analytics:start — managed by work/scripts/configure_site.py, do not edit by hand -->"]
    lines += body
    lines.append("<!-- analytics:end -->")
    return "\n".join(indent + line if line else line for line in lines)


def rewrite(path, old_base, new_base, provider, ident, verify):
    """Return (text, [what changed]) for one served file."""
    text = path.read_text(encoding="utf-8")
    changed = []

    if old_base != new_base:
        n = text.count(old_base)
        if n:
            text = text.replace(old_base, new_base)
            changed.append(f"{n} absolute URL(s) -> {new_base}")

    # analytics: the whole marked block is regenerated from the config
    def swap(m):
        return analytics_block(provider, ident, m.group(1))

    before = text
    text, n = BLOCK.subn(swap, text)
    if n == 0 and path.suffix == ".html":
        changed.append("WARNING: no analytics:start/end markers — analytics left untouched")
    elif text != before:
        changed.append(f"analytics -> {provider or 'none'}{(' ' + ident) if ident else ''}")

    # badge link
    if verify is not None:
        before = text
        text = re.sub(
            r'(<a class="grad-badge"[^>]*?href=")[^"]*(")',
            lambda m: m.group(1) + (verify or "#badge-not-configured") + m.group(2),
            text,
        )
        if text != before:
            changed.append("badge verify link updated")

    return text, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="canonical base URL, no trailing slash")
    ap.add_argument("--go-live", action="store_true", help="use base_url_target from site.json")
    ap.add_argument("--analytics", help="GA4 measurement ID, GoatCounter site code, or 'none'")
    ap.add_argument("--verify", help="badge verification URL")
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    cfg = load()
    old_base = cfg["base_url"].rstrip("/")

    new_base = old_base
    if args.go_live:
        new_base = cfg["base_url_target"].rstrip("/")
    if args.base:
        new_base = args.base.rstrip("/")

    if args.analytics is not None:
        provider, ident = read_analytics(args.analytics)
    else:
        provider, ident = read_analytics(cfg.get("analytics_id", ""))
    verify = args.verify if args.verify is not None else cfg.get("badge_verify_url", "")

    if not new_base.startswith("https://"):
        sys.exit(f"base URL must start with https:// — got {new_base!r}")

    print(f"base      {old_base}" + (f"  ->  {new_base}" if new_base != old_base else "  (unchanged)"))
    print(f"analytics {f'{provider} {ident}' if provider else '(unset — no analytics will load)'}")
    print(f"badge     {verify or '(unset — badge link is a placeholder)'}")
    print()

    dirty = False
    for rel in TARGETS:
        path = DOCS / rel
        if not path.exists():
            print(f"  skip {rel} (missing)")
            continue
        text, changed = rewrite(path, old_base, new_base, provider, ident, verify)
        if changed:
            dirty = True
            print(f"  {rel}: " + "; ".join(changed))
            if not args.check:
                path.write_text(text, encoding="utf-8")
        else:
            print(f"  {rel}: already current")

    # The paper's URL is a required deliverable: exactly one line, and it has to
    # follow the site to its new address.
    paper_url = ROOT / "submission" / "paper_url.txt"
    want = f"{new_base}/\n"
    print()
    if paper_url.read_text() != want:
        print(f"  submission/paper_url.txt: -> {new_base}/")
        if not args.check:
            paper_url.write_text(want, encoding="utf-8")
        dirty = True
    else:
        print("  submission/paper_url.txt: already current")

    # CNAME tells GitHub Pages which host to serve. It must NOT exist until DNS
    # for that host actually resolves — otherwise Pages serves the custom host
    # (404) and redirects the github.io address to it, taking the site down.
    host = new_base.split("://", 1)[1].split("/", 1)[0]
    on_github_pages = host.endswith("github.io")
    print()
    if on_github_pages:
        if CNAME.exists():
            print(f"  CNAME: removing (base is {host}, no custom domain)")
            if not args.check:
                CNAME.unlink()
            dirty = True
        else:
            print("  CNAME: absent, correct for a github.io base")
    else:
        want = host + "\n"
        if not CNAME.exists() or CNAME.read_text() != want:
            print(f"  CNAME: writing {host}")
            if not args.check:
                CNAME.write_text(want, encoding="utf-8")
            dirty = True
        else:
            print(f"  CNAME: already {host}")

    if not args.check:
        cfg["base_url"] = new_base
        cfg["analytics_provider"] = provider
        cfg["analytics_id"] = ident
        cfg["badge_verify_url"] = verify
        save(cfg)

    print()
    if args.check:
        print("CHECK ONLY — nothing written." if dirty else "CHECK ONLY — already in sync.")
    else:
        print("site.json applied." if dirty else "Nothing to change; already in sync.")


if __name__ == "__main__":
    main()
