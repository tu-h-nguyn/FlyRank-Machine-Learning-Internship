# Going live — domain, analytics, badge

Everything on the page side is built and verified. What is left needs three accounts
that only you can open, and DNS that only you can point. Each step ends in one command.

Where the values live: **`work/portfolio/site.json`**. Nothing else needs editing —
`work/scripts/configure_site.py` stamps them into every served file, and
`work/scripts/audit_launch.py` tells you whether it worked.

```bash
python3 work/scripts/audit_launch.py     # what is still unset, and why it matters
```

Right now that reports exactly two gaps: the analytics code and the badge link.

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
python3 work/scripts/configure_site.py --base https://tu-h-nguyn.github.io/FlyRank-End-to-End-Machine-Learning-Project-Internship
```

## 2. Analytics — GoatCounter

Free for personal use, about 3 KB, sets no cookies and stores no personal data, so it
needs no consent banner. While the code is empty the page loads no analytics script at
all — worth knowing, because it means an unconfigured site is not quietly half-tracking.

1. Sign up at `goatcounter.com` and pick a code — say `hoangtu`. Your dashboard is then
   `https://hoangtu.goatcounter.com`.
2. ```bash
   python3 work/scripts/configure_site.py --analytics hoangtu
   ```
3. Commit, push, wait a minute or two, then open the live site in a private window and
   reload twice.
4. Open your dashboard. The visits should be there within about 30 seconds.
   **Screenshot that dashboard showing non-zero visits** — that is the deliverable, not
   a screenshot of the script tag.

If the dashboard stays empty: an ad blocker will block `gc.zgo.at`, so test with one off.

## 3. The graduate badge

The badge is drawn and installed in the footer of both pages
(`docs/assets/flyrank-graduate-badge.svg`) — it is served from your own repo, so it cannot
break when someone else's host goes down. What is missing is where it points.

I could not open `internship-badge.netlify.app` from the build environment to read your
verification URL, so the link is a placeholder and both audits fail on it deliberately.

```bash
python3 work/scripts/configure_site.py --verify https://<your-verification-page>
```

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
links to your verification page, and a visit showing in the GoatCounter dashboard.
