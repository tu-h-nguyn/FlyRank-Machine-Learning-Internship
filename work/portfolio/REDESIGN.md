# Portfolio redesign — audit, architecture, evidence

The brief: turn the portfolio into an evidence-based technical portfolio with the
identity *Mathematics × Computer Science × AI × Quantitative / Computational
systems*. Nothing is claimed that a repository cannot show. This file records what
was found, what was decided, and where every number comes from.

## 1. Audit of the site as it was (September 2026)

**Stack.** One hand-written static page, `docs/portfolio/index.html` (~110 KB: inline
CSS, two inline scripts, three generated inline SVG figures), no framework, no build.
Published to `https://tu-h-nguyn.github.io/` by `export_user_site.py` through the
`deploy-user-site` workflow. Tooling around it: `configure_site.py` (analytics),
`make_project_figures.py`, `make_portfolio_og.py`, and three test suites
(`audit_portfolio.py`, `test_contact_form.py` — 33 checks, `harden_portfolio.py` —
26 checks).

**Keep — this is working.**
- Content discipline: every project states a problem, an approach and a measured result;
  the "code not public" items are labelled as background, not evidence.
- The evidence itself: figures generated from each project's data, CI-checked numbers,
  the honest-vs-leaky ranking result.
- Engineering: contact form with progressive enhancement and a browser test suite;
  WCAG AA contrast; reduced-motion support; no-JS rendering; Vietnamese-safe fonts.
- Palette (ink / navy / slate on paper) and Playfair Display for display type.

**Weak.**
- *Positioning.* The hero said "Machine Learning Engineer / AI Engineer" and the page read
  as an ML-internship application. The mathematics — the actual differentiator (a theory
  thesis, three numerical-analysis repositories, an optimisation study) — was buried in
  project 2 onwards.
- *Hierarchy.* One 2,000-line page: 7 long project cards at equal weight; a visitor had to
  scroll ~8 screens to learn what the work was about.
- *The thesis* — the deepest piece of work — sat as card 5 of 6 with no figure.
- *Skills* listed tools, then pointed at evidence in a second line; the grouping was by tool
  family, not by capability.
- *Missing work.* Two public repositories were not on the page at all:
  **AI-Quant-Trading-System** and **Enterprise-Hybrid-RAG** — including the only
  quantitative-finance evidence there is.

**Redundant / decorative.** The "Who I am" box, the typographic "Tú" portrait, the
marquee of keywords, the floating squares and the pointer parallax were template
decoration (the look was taken from an agency template on request). They carried no
information and competed with the content.

**Missing.** Research interests, a writing index (six real long-form documents exist and
none were listed together), a CV, a dedicated thesis page, categories for projects,
dark mode, per-page SEO.

**Highest-impact changes, in order.**
1. Re-position the hero on the mathematics and name the three strands in one line.
2. Make projects the centre: a featured set of five on the home page, the full catalogue
   with Problem → Method → Implementation → Result on its own page.
3. Make the thesis the flagship with its own page, its real notation and its six
   pre-registered experiments.
4. Add the two missing repositories.
5. Skills rewritten as capability → what was built → where to check it.
6. Research, Writing and CV as their own sections/page.

## 2. Information architecture

```
/              Home — the summary a recruiter reads in 20 seconds
  #projects      Featured projects (5) → link to /projects/
  #research      Research directions, each tied to the work that asks it
  #writing       Reports, papers, write-ups — all real; planned notes marked as planned
  #skills        Capability → evidence
  #about         Education, method, now
  #contact       Form + links
/projects/     All eight public projects by category, full detail and figures
/thesis/       Flagship: the thesis, its mathematics, its experiments
/cv/           Print-ready résumé built from the same facts (Print → Save as PDF)
```

Navigation: Projects · Research · Writing · Skills · About · CV — six items, no dropdowns.
Sub-pages link back to the home sections.

## 3. Visual direction

Research lab × quantitative engineering × technical documentation, built on what was
already right:

- **Type, three families, fixed roles.** Playfair Display for H1/H2 only (the "paper"
  voice); Be Vietnam Pro for body and H3; JetBrains Mono for labels, figures, code,
  section indices. All three ship Vietnamese glyphs. Mathematics in native MathML — no
  library, readable by screen readers, rendered in the system math font.
- **Colour.** Ink / navy / slate on warm paper in light; a navy-black ground in dark
  (follows the system, with a toggle). Every text pair AA in both.
- **Grid.** 1200 px max, 12 columns, hairline rules, mono indices — the page reads like
  a well-set technical document.
- **Mathematics as identity, not wallpaper.** The hero shows the thesis's own computational
  graph (forward pass, then the reverse-mode pass) and its update rule; the thesis page
  shows its actual equations. Nothing mathematical appears that the work does not use.
- **Motion, subtle.** Sections fade in; data figures sweep along their time axis; the hero
  graph runs its two passes once. All of it off under `prefers-reduced-motion`.

## 4. Keep / change / remove / add

| | |
|---|---|
| Keep | Project content and numbers, generated figures, contact form + tests, palette, Playfair |
| Change | Hero, section order, skills format, project cards (categories + structure), title/SEO, footer |
| Remove | "Who I am" box, typographic portrait, marquee, parallax squares, count-up numbers |
| Add | Thesis page, projects page, CV page, research, writing, dark mode, the 2 missing repos |

## 5. Evidence inventory — where every number comes from

| Claim on the site | Source |
|---|---|
| 8 public repositories, each with CI | GitHub, `.github/workflows/` of each repo (checked 2026-09-23) |
| 5 re-derive their published numbers in CI | FEM `verify.yml`, Euler, LMM, PINNs `ci.yml`, PPA `build.yml` (as stated on the site before; unchanged) |
| Thesis: 6 experiments, criteria fixed in advance; 20 tests; 39 checks; 885 lines of method code | thesis repo README, `code/tests/`, `code/verify_results.py`, `wc -l code/pinns/*.py` = 885 |
| TN1–TN6 results | thesis README results table; TN3 ratios (24×, 4×) recomputed from `exp3_spectral.json` |
| Ranking: 18,010 pages, 0.88 precision@50, 0.74 baseline | `work/outputs/capstone_metrics.json` (this repo) |
| RAG: 50 questions, 22 documents, Recall@1 0.585 / 0.643 / 0.643 / 0.795 | `enterprise-hybrid-rag/data/evaluation/results.json` as committed |
| Quant trading: methodology only, **no performance numbers** | the repo commits no results; they are generated by its research workflow |
| FEM, Euler, PPA numbers | carried over from the previous page; the PPA figure recomputed (see `make_project_figures.py`) |
| LMM: 93 tests | `pytest --collect-only` in the LMM repository = 93 (the previous page said 86; the suite has grown); the figure recomputed from the method's coefficients |
| 6 long-form documents | the six linked in Writing: the paper, the thesis, and the FEM, LMM, Euler and RAG reports |
| Euler: 133 tests, 98% coverage | the Euler repository's README badges |

## 6. Deliberately not claimed

- **C++, SQL, Linux** — asked for in the brief, but no public repository demonstrates them.
- **"Implemented reverse-mode autodiff from scratch"** — the thesis *derives* forward and
  reverse mode; the implementation is built on `torch.autograd`. The site says exactly that.
- **Trading performance** (returns, Sharpe) — none is committed; none is shown.
- **Explainable AI, risk modelling** as headline skills — the evidence is narrower
  (permutation importance; volatility targeting and drawdown guardrails) and is described
  as what it is.
- Awards, certifications, publications, stars, users — there are none to cite.

## 7. Content the owner should add

- A **CV PDF** (the `/cv/` page prints to one; a hand-tuned PDF would be better).
- **Current focus** — what is being built now. Left out rather than invented.
- **English notes** from the thesis (backpropagation as vector–Jacobian products;
  forward vs reverse mode; the spectral-bias reversal). Listed as planned, not published.
- A **compiled thesis PDF** in the thesis repository (only LaTeX source is committed).
- A photo, if wanted (`/about` has none by design).

## 8. How the site is built

No framework: one standard-library script assembles the pages from shared parts.

```
work/portfolio/site/
  layout.html        head, nav, footer — shared by every page
  styles.css         the one stylesheet, inlined into each page
  site.js            theme, nav, reveal, contents highlight, project filter, menu, print
  form.js            the contact form (home page only)
  pages/*.html       index, projects, thesis, cv — each body opens with a JSON header
work/portfolio/figure-data/          the data behind the inline figures, with provenance
work/scripts/make_project_figures.py figure data  -> the figure blocks in pages/*.html
work/scripts/build_portfolio.py      pages + layout -> docs/portfolio/**/index.html
work/scripts/export_user_site.py     docs/portfolio -> the tu-h-nguyn.github.io repository
```

The edit loop:

```bash
python3 work/scripts/make_project_figures.py   # only when figure data changed
python3 work/scripts/build_portfolio.py
python3 work/scripts/audit_portfolio.py && python3 work/scripts/audit_launch.py
python3 work/scripts/test_contact_form.py && python3 work/scripts/harden_portfolio.py
```

`portfolio-check` fails a pull request whose built pages or figures are stale against
their sources; `deploy-user-site` refuses to publish in the same case.

## 9. Decisions after review

- **Removed: the "Numbers you can re-run" band and the keyword marquee** of the live
  site. Four numbers from one project, and a scrolling list of keywords, said nothing
  about the portfolio as a whole. In their place: four portfolio-wide facts in the hero
  (8 repositories with CI, 5 re-deriving their numbers, 6 long-form documents, 1 theory
  thesis); "How I work" rewritten as one method with a link to each project where it
  shows; the honest-vs-leaky ranking story kept inside the ranking entry, where it is
  evidence for that project.
- **The share card** (`og.png`) was redrawn with the same portfolio-wide facts; it had
  still said "Machine Learning / AI Engineer" and quoted the ranking metrics. On the
  owner's request it shows a world map with Việt Nam magnified (Natural Earth outlines,
  vendored in `work/portfolio/og-map/`; Hoàng Sa and Trường Sa marked as Vietnamese maps
  show them) instead of the computational graph, which stays in the page's hero.
- **Accessibility found by the extended audits** (see `WHERE-IT-BREAKS.md` §8–11): text
  inside figures below 4.5:1, 200% text overflow on every page, over-long metadata, a
  prime that rendered as a speck. All fixed; the audits now cover every page, both themes.
