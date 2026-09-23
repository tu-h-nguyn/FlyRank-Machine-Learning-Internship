# Going live — domain, analytics, badge

Everything on the page side is built and verified. What is left needs three accounts
that only you can open, and DNS that only you can point. Each step ends in one command.

Where the values live: **`work/portfolio/site.json`**. Nothing else needs editing —
`work/scripts/configure_site.py` stamps them into every served file, and
`work/scripts/audit_launch.py` tells you whether it worked.

```bash
python3 work/scripts/audit_launch.py     # what is still unset, and why it matters
```

Right now it reports no blocking issues: analytics and the badge link are both configured.
The one thing left is the domain, and that waits on DNS you have to point yourself.

---

## 1. The domain — `hoangtu.is-a.dev`

`is-a.dev` gives developers a free subdomain. It is a real domain on the public suffix
list, it gets a proper HTTPS certificate, and it costs nothing. The name is a placeholder
I picked — change `base_url_target` in `site.json` if you want a different one.

**Do not add the CNAME file before DNS resolves.** If GitHub Pages sees a custom domain
that does not resolve, it serves that host (404) *and* redirects your `github.io` address
to it. The site goes dark until DNS catches up. That is why the repo is still canonical on
`github.io` today, and why the switch is one command you run *after* the domain works.

1. Fork **`is-a-dev/register`** on GitHub.
2. Copy `work/portfolio/is-a-dev/hoangtu.json` into that fork as
   `domains/hoangtu.json`, renaming it if you chose a different subdomain.
3. Put a real email in the `owner.email` field — that file is public, so use an address
   you are willing to publish. It is the only thing in it you must change.
4. **Check the schema against the register repo's own README before you open the PR.**
   I could not reach `is-a.dev` from the build environment to verify it (the egress proxy
   blocks it), so the field names in that file are from memory — the repo has used both
   `record` and `records` at different times, and it may now want a `proxied` flag. If it
   does, set it to `false`: Cloudflare's proxy in front of GitHub Pages interferes with
   Pages issuing its own certificate.
5. Open the PR and wait for it to merge (usually a day or two).
6. Confirm DNS actually resolves before touching the repo:
   ```bash
   dig +short hoangtu.is-a.dev      # must return tu-h-nguyn.github.io / GitHub's IPs
   ```
7. Only once that returns something, flip the site over:
   ```bash
   python3 work/scripts/configure_site.py --go-live
   git add -A && git commit -m "Go live on hoangtu.is-a.dev" && git push
   ```
   That rewrites every canonical tag, `og:url`, share-image URL and sitemap entry, and
   writes `docs/CNAME`.
8. In **Settings → Pages**, confirm the custom domain is filled in and tick
   **Enforce HTTPS**. The certificate takes a few minutes; the tickbox is greyed out
   until it is issued, which is normal.

To back out at any point:

```bash
python3 work/scripts/configure_site.py --base https://tu-h-nguyn.github.io/FlyRank-Machine-Learning-Internship
```

## 2. Analytics — done, on GA4

Both pages count visits with **Google Analytics 4, `G-KGRCWRY9BV`**. It is stamped in and
the audit passes on it; nothing here is blocking. The rest of this section is how to
change it.

One counter, one place: `analytics_provider` and `analytics_id` in `site.json`. The block
between the `analytics:start` and `analytics:end` comments on each page is *generated* —
by `configure_site.py` on the portfolio and by `build_paper.py` on the paper — so never
edit it by hand; the next run overwrites you. That is also why the pages cannot end up
shipping two counters at once, or a dead snippet that loads nothing: the audit fails on
both.

```bash
python3 work/scripts/configure_site.py --analytics G-ABC1234567   # a different GA4 property
python3 work/scripts/configure_site.py --analytics hoangtu        # switch to GoatCounter
python3 work/scripts/configure_site.py --analytics none           # no counter at all
python3 work/scripts/build_paper.py                                # carry it into the paper
```

Then commit, push, wait a minute or two, open the live site in a private window, reload
twice, and check the dashboard. **Screenshot the dashboard showing non-zero visits** —
that is the deliverable, not a screenshot of the script tag. GA4's standard reports can
lag up to a day; look at **Realtime**, which shows the visit within about a minute.

If the dashboard stays empty it is almost always an ad blocker — `googletagmanager.com`
and `gc.zgo.at` are on every blocklist. Test with one off.

**One thing to know about GA4.** It sets cookies and sends data to Google, so in the EU/UK
it needs a consent banner to be lawful, and this site ships none. For a portfolio read by
recruiters that is a judgement you are making, not an oversight — but it is why the
cookieless alternative is kept one command away. GoatCounter is free for personal use,
about 3 KB, sets no cookies and stores no personal data, so it needs no banner.

## 3. The graduate badge

The badge is drawn and installed in the footer of both pages
(`docs/assets/flyrank-graduate-badge.svg`) — it is served from your own repo, so it cannot
break when someone else's host goes down. It links to your FlyRank verification page
(`internship.flyrank.ai/verify?id=FR-D2-T779H-R890R`), which is set and passing the audit.

To point it somewhere else:

```bash
python3 work/scripts/configure_site.py --verify https://<your-verification-page>
```

The one check that cannot be done from here: open that link on the live site and confirm
it loads *your* credential page, not a 404 or someone else's.

If FlyRank supplies its own badge image and you would rather use theirs, replace
`docs/assets/flyrank-graduate-badge.svg` with it — same filename, and nothing else changes.

## 4. Launch hygiene — already done, but confirm on the real address

These are wired and pass the offline audit; three of them can only be *confirmed* against
a live URL:

- **Share preview.** Both pages have a full Open Graph and Twitter card with a 1200×630
  image. The portfolio's is `og.png`; the paper's is `og-paper.png`, regenerate with
  `python3 work/scripts/make_paper_og.py`. Paste the live URL into a share-preview
  debugger and confirm the card renders. Note that these debuggers cache aggressively —
  if you have shared the old address before, use their "scrape again" button.
- **Favicon.** `docs/favicon.svg` for the paper, `docs/portfolio/favicon.svg` for the
  portfolio. Confirm the tab icon on the real address, not on a `file://` copy.
- **Titles.** "The 30-Day Decline Queue" and "Nguyễn Hoàng Tú — Machine Learning / AI
  Engineer Intern". Distinct, both under 60 characters.
- **On your phone.** Open the final address once on the actual device. Check the badge is
  not cut off and the footer text is readable.

## The checklist that marks this done

```bash
python3 work/scripts/audit_launch.py      # must print NO BLOCKING ISSUES
python3 work/scripts/audit_portfolio.py   # must print NO ISSUES FOUND
```

Then, on the live URL, in a private window: HTTPS padlock, share preview, favicon, badge
links to your verification page, and a visit showing in the analytics dashboard
(GA4 → **Realtime**, unless you switched the counter).
