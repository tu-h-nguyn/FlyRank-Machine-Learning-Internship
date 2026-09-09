# Where it breaks

Hardening pass on the portfolio and its contact form. The goal was to break my own
site, not to confirm it works — so this is written around what failed, not what passed.

Everything below is reproducible:

```
python3 work/scripts/harden_portfolio.py     # the adversarial pass
python3 work/scripts/test_contact_form.py    # the happy path + obvious failures
python3 work/scripts/audit_portfolio.py      # links, contrast, SEO, assets
```

---

## What I tried

Not just an empty form. The list I actually ran:

**The form** — empty submit · whitespace-only fields · `<script>alert(1)</script>` and
`<img src=x onerror=...>` in name and message · `'; DROP TABLE users;--` · emoji and
right-to-left Arabic · 40 stacked combining marks on my own name · `user@localhost` (no
TLD) · `a@@b.co` · an address with a leading space · a 9,000-character message · a
400-character unbroken word · clicking Send twice with zero delay · hammering Enter five
times · sending a second message straight after the first.

**The page** — every nav link and every outbound link · JavaScript switched off · 320px
and 360px screens · 200% text zoom · keyboard-only navigation including whether the
honeypot can be reached by Tab.

Three things broke.

---

## Fixed

### 1. The sticky nav swallowed every in-page link — *serious*

Clicking **Projects**, **Approach**, **Skills** or **Contact** scrolled the section to
`top: 0`, directly underneath the 47px sticky bar. The heading you just asked for was
the one thing hidden. Every single nav link was affected, so any recruiter using the
nav landed on a page that looked broken.

I did not catch this by looking. I caught it by measuring the heading's position against
the nav's height after a programmatic click.

**Fix:** `scroll-margin-top: 4rem` on every section.
**Evidence:** heading top went from `-0px` (under a 47px nav) to `64px` (clear of it) on
all four links.

### 2. Email validated trimmed, but sent untrimmed

Validation ran on `value.trim()`, while the payload was built from the raw field. So
` me@example.com` passed the check and arrived at my inbox with the leading space still
attached — which is exactly the field Web3Forms uses for reply-to. The message would
land, and replying to it would fail.

A quiet one: nothing errors, nothing looks wrong, and you only find out when a reply
bounces.

**Fix:** trim string values when building the payload.
**Evidence:** the harden suite now asserts the delivered address is exactly `a@b.co`.

### 3. Nav row overflowed at 200% text zoom

At 200% font size on a 390px screen the page scrolled sideways — 391px of content in a
390px viewport, caused by the four nav links refusing to wrap. One pixel, but horizontal
scrolling at 200% zoom is a WCAG 1.4.10 reflow failure, and people who zoom are exactly
the people it hurts.

**Fix:** `flex-wrap: wrap` on the nav row.
**Evidence:** no horizontal scroll at 2× font size.

---

## Tried and did not break

Worth recording, because "I tested it" means nothing without the list:

| Attack | Result |
|---|---|
| Double-click Send, zero delay | one email — the button disables synchronously |
| Enter pressed five times | one email |
| `<script>` / `<img onerror>` in fields | delivered as plain text, nothing executes |
| SQL injection strings | delivered as text |
| Emoji, Arabic RTL, 40 combining marks | delivered intact, no mangling |
| Whitespace-only fields | rejected client-side |
| `user@localhost`, `a@@b.co` | rejected client-side |
| 9,000-character message | capped at 3,000 by the browser |
| 400-character unbroken word | does not widen the page |
| JavaScript off | form still posts natively; no spurious warning |
| 320px and 360px screens | no horizontal scroll |
| Keyboard only | every control reachable; honeypot never focusable |
| Second message, same session | works |

### 4. No `<main>` landmark — found by Lighthouse

The page wrapper was a plain `<div>`. Screen readers use landmarks to let people jump
straight past the navigation to the content, and there was nothing to jump to — my own
"Skip to content" link pointed at an element that carried no landmark role. Lighthouse's
accessibility audit caught it; I had not thought to look.

**Fix:** `<div class="wrap" id="main">` became `<main class="wrap" id="main">`.
**Evidence:** Lighthouse accessibility went 98 → **100** on a re-run; the main-landmark
audit was the only accessibility failure in the first run, and the only imperfect audit
left afterwards is the blocked-font console error described under Speed.

---

## Known limitations — not fixed, not hidden

**1. There is no server-side validation, and there cannot be.** Every check runs in the
browser. Anyone can read my access key in the HTML and POST straight to Web3Forms,
skipping all of it. I accept this: the key is an address, not a credential, so the worst
case is junk in my own inbox. If it becomes a problem I rotate the key.

**2. The honeypot only catches naive bots.** It stops scripts that parse HTML and fill
every field. A bot that renders CSS, or one aimed at this form specifically, walks
through it.

**3. I control no rate limit.** The free tier is 250 messages a month. Someone
determined could burn through that, and then the form **silently stops delivering** until
the quota resets — with no alert to me and a green "message sent" shown to the visitor.
This is the failure I would fix first if the site mattered commercially.

**4. `robots.txt` cannot work here.** Crawlers only read it at the domain root
(`john-hcmus.github.io/robots.txt`), which I do not control — this is a project page on
a shared domain. I shipped `sitemap.xml` instead and will submit it manually through
Search Console. A custom domain would remove this limitation.

**5. Google Fonts is a third-party render-blocking dependency.** On a slow or restricted
network the page renders in fallback fonts. Mitigated with `preconnect` and
`display=swap`, so text is never invisible — but the layout does shift slightly when the
webfont lands.

**6. Speed is measured on localhost, not in the world.** Numbers below are honest about
what they exclude.

**7. Tested in Chromium only.** No real iOS Safari, no real Android device. Safari is
the gap I would most like to close.

**8. Analytics is a page counter, not a funnel.** GA4 is installed, so visits are visible
— but nothing on the page is instrumented, so I still cannot tell where a reader drops off
or which project sent them to GitHub. GA4 also sets cookies and the page ships no consent
banner; `GO-LIVE.md` explains the trade and keeps a cookieless counter one command away.

**9. Three of five projects have no repository link,** and the Transformer project's
result has no number attached. On a page that argues from evidence, those are the weak
items — named here rather than quietly left.

---

## SEO and meta added

| Item | Value |
|---|---|
| `<title>` | 55 chars, name + target role |
| `<meta description>` | 149 chars — under the ~155 Google shows |
| Canonical URL | set |
| `robots` | `index, follow, max-image-preview:large` |
| Open Graph | title, description, url, type, locale, site_name |
| `og:image` | real 1200×630 PNG, absolute URL, with `og:image:alt` |
| Twitter | `summary_large_image` |
| JSON-LD | `Person` — job title, `knowsAbout`, `sameAs` → GitHub + LinkedIn |
| Favicon | inline SVG monogram |
| Sitemap | `docs/sitemap.xml`, both pages |

The share image is generated, not a screenshot: name, target role, one-line value
proposition, and the three numbers that matter (18,010 · 0.88 · public paper + code).
The audit script asserts it is exactly 1200×630 so it can never silently rot.

## Speed

Two measurements, and they disagree — which is the honest part.

### Lighthouse 13.4.1 (mobile, simulated throttling)

Run with the real Lighthouse binary against the real page, so these are the same audits
PageSpeed Insights runs for its lab section.

| Category | Score |
|---|---|
| Performance | **90** |
| Accessibility | 98 → **100**, confirmed by a second run after the `<main>` fix |
| Best Practices | **96** |
| SEO | **100** |

| Metric | Value |
|---|---|
| First Contentful Paint | 1.5 s |
| Largest Contentful Paint | 1.5 s |
| Total Blocking Time | **0 ms** |
| Cumulative Layout Shift | **0** |
| Time to Interactive | 1.5 s |

Zero blocking time and zero layout shift are the two I care about: nothing on this page
blocks the main thread, and nothing jumps around while it loads.

**Three results in that run are artefacts of my build environment, not real:**

- **Speed Index 19.6 s.** The sandbox has no outbound network, so the Google Fonts
  request hangs until it resets. Speed Index measures visual completeness over time, so
  a hanging request destroys it. On a real network this number will be close to FCP.
- **"Browser errors were logged to the console."** One error:
  `net::ERR_CONNECTION_RESET` — the same blocked font request. There are no JavaScript
  errors; the other suites assert that separately.
- **"Document request latency, est. savings 27 KiB."** My local `http.server` sends no
  compression. GitHub Pages serves gzip/brotli automatically, so this disappears in
  production.

**Two are real and I am choosing not to fix them:**

- **Render-blocking request, ~650 ms** — the Google Fonts stylesheet. Removing it means
  self-hosting the fonts or dropping them. Already mitigated with `preconnect` and
  `display=swap`, so text paints immediately in a fallback face.
- **"Minify CSS, est. savings 3 KiB."** The CSS is inlined and hand-maintained. Three
  kilobytes is not worth making the only stylesheet unreadable on a page I edit by hand.

### Raw payload, over localhost

| Metric | Value |
|---|---|
| Visitor payload | **41 KB** total (HTML + favicon) |
| DOM nodes | 234 |
| Requests | 3 — document, favicon, Google Fonts |

No images on the page, no frameworks, no CSS or JS files: everything is inlined in one
document. The 62 KB `og.png` is fetched only by social crawlers, never by a visitor.

---

## Still needs a human

Three things I could not do myself, and why:

1. **A PageSpeed Insights run against the live URL.** Lighthouse has now been run
   locally (above), which covers the lab audits — but PSI also reports field data from
   real Chrome users, and it measures over a real network rather than localhost.
2. **Searching my own name to check findability.** Indexing takes days to weeks after
   the meta went live; the sitemap still needs submitting to Google Search Console.
3. **The hardening review itself** — a mentor or structured peer read of this document
   and the fixes. Their must-fixes get added here as a new section.
