# Capstone Report — Lane 2: Refresh / Content Opportunity Scoring

- **Author:** John (nguyenhoangtuk23hcmus@gmail.com)
- **Lane:** Lane 2 — Refresh / Content Opportunity Scoring
- **Repo:** https://github.com/tu-h-nguyn/FlyRank-End-to-End-Machine-Learning-Project-Internship
- **Deployed paper:** see `submission/paper_url.txt`
- **Date:** 2026-08-27
- **Seed:** 42 · **Everything below is produced by** `work/scripts/capstone_pipeline.py`

---

## 0. Abstract

When an editorial team can review only a few dozen pages a week, the real question is not "which
pages are bad" but "which pages should be looked at first". I used the public anonymized FlyRank
starter slice (30,000 pages × 44 columns, 32 pseudonymized clients, one trailing 90-day snapshot),
split the 90-day window into three exact 30-day sub-windows, and kept only the signals that were
knowable at the decision point to rank pages by their risk of losing more than 20% of search
impressions over the next 30 days. A logistic regression over 24 such features, scored out-of-fold
under a client-grouped split, put **88% real decliners in its top 50** against **74%** for a
transparent rule baseline and a **61.6%** base rate — while my own Week-4 rule turned out to score
only 12 of 18,010 pages above zero and therefore rank nothing (ROC-AUC 0.500). Adding the
window-overlapping columns back lifted precision@200 to 0.995, a beautiful number that is a leakage
confession rather than a result. The deliverable is an 18,010-row action queue carrying reason
codes, a suggested action and a confidence label, built to **support the order of human review** —
not to promise that refreshing a page recovers its traffic.

---

## 1. Problem framing

**Decision supported.** An editor with capacity for ~50 pages a week must choose the *order* of
review across a large content portfolio.

**Unit of analysis (grain).** One pseudonymized content item (`content_id`) in one snapshot.

**Output.** A ranked queue: risk score + reason codes + suggested action + confidence label.

**Action a human takes.** Open the top of the queue, apply the human review gates (business value,
consolidation, seasonality, evergreen check, reachable position), and refresh / fix metadata /
protect / monitor accordingly.

**Cost of a wrong call.**
- *False alarm* — an editor spends an hour on a page that did not need it, and disturbs a page that
  was stable.
- *Miss* — a page with real demand decays quietly until recovery is expensive.

Because those costs are asymmetric in K, the metric is **precision@K at the team's real capacity**,
always printed next to the base rate.

**Why ML at all.** The decision needs an ordering across ~18,000 pages using several weak, noisy,
correlated signals at once. A threshold rule can select a group; it cannot order one.

---

## 2. Data safety

**Used.** `data/raw/content_refresh_anonymized.csv` — the public anonymized starter slice
(30,000 pages, 32 pseudonymized clients, one rolling 90-day GSC + GA4 window).

**Not used, and why.** The full ~79M-row warehouse release is gated and needs an `HF_TOKEN`;
the environment this capstone ran in had no token. The feature contract is source-agnostic —
`cp.load_raw()` is the only function that changes — but the published numbers are from the public
slice. Stated as a limitation, not hidden.

**The window decomposition (the finding that unlocks everything).**

```text
impressions_90d = first30 (days 61-90 back) + prev30 (days 31-60 back) + last30 (days 1-30 back)
                  \_______ knowable _______/   \______ knowable ______/   \___ LABEL WINDOW ___/
```

Verified exactly in the notebook: max reconstruction error = 0. Every `*_90d` total therefore
*contains* the label window and is illegal as a feature; `first30` and `prev30` are legal.

**Excluded columns (full list with reasons is in `work/outputs/capstone_metrics.json` →
`features_excluded`).** Label-derived (`trend_pct`, `trend_direction`); all 90-day totals and rates
(`impressions_90d`, `clicks_90d`, `ctr`, `avg_position`, `engagement_rate`, `scroll_rate`,
`ai_traffic_pct`, `days_with_impressions`, …); all last-30-day columns; product tiers
(`impression_tier`, `position_tier`, `freshness_tier`); production metadata (`provider_used`,
`model_used`); and the IDs, which are used only for grouping and splitting.

**The hardest exclusion — `days_since_last_update`.** It is exactly the signal my Week-4 rule leaned
on, but it is measured at export time and **20,480 of 30,000 pages (68.3%) were updated inside the
outcome window**. It knows the future. Excluded.

**Population filter.** `impressions_prev_30d >= 100` — a minimum-demand floor so a decline is worth
an editor's hour. Drops 11,990 pages, leaves **18,010 pages across 30 clients**. The filter reads
only pre-decision columns, so it carries no outcome-window information; it does narrow what the
results can speak about, which is stated in the limitations.

**Public safety.** No client names, domains, URLs, titles or queries appear in any output. Only
pseudonymous IDs and aggregates. Verified by a column scan in the capstone notebook.

---

## 3. Baseline

**The frozen Week-4 rule (kept exactly as written).**
`stale (days_since_last_update >= 180) × visible (impressions_90d >= 1000) × valid position ×
impressions_90d`. Kept unchanged on purpose — it reads two contaminated columns, and showing what
that costs is part of the result.

**The legal rule baseline (same idea, decision-time columns only).** In plain words: *a page is worth
reviewing first if it already lost ground between the two windows an editor can see, and it still
carries enough demand to matter* — with a small penalty when its prior-window CTR is below the
median. No fitted weights.

Both are evaluated on the same 18,010 rows, the same label, the same metrics as the model.

| Baseline | P@20 | P@50 | P@200 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|
| Random ordering | 0.700 | 0.580 | 0.635 | 0.6169 | 0.4980 |
| Week-4 rule (contaminated) | 0.850 | 0.720 | 0.615 | 0.6159 | 0.5004 |
| Legal rule baseline | 0.900 | 0.740 | 0.730 | 0.6676 | 0.5621 |

Base rate = 0.6155 for every row above.

---

## 4. Model / analysis

**Task type.** Ranking / scoring, evaluated at precision@K — not a yes/no classification problem,
even though the label is binary.

**Label (one sentence).** `label_declined = 1` when impressions in the most recent 30 days fell more
than 20% versus the previous 30 days (the product's own `trend_direction == "down"` definition).

**Method.** Logistic regression (standardised) as the readable model; random forest
(300 trees, depth 8, min_samples_leaf 50) as the stronger-complexity comparison. The logistic
regression won on the honest split, so it is the shipped model — complexity has to earn its keep.

**Features — 24 columns, all knowable at the decision point:**

| Group | Columns |
|---|---|
| Demand level | `log_impr_prev30`, `log_impr_first30`, `log_clicks_prev30`, `log_sessions_prev30` |
| Prior momentum | `prior_impr_trend_pct`, `prior_click_trend_pct`, `prior_session_trend_pct`, `impr_share_prev30` |
| Click capture | `prior_ctr`, `prior_ctr_delta`, `sessions_per_1k_impr_prev30` |
| Content | `content_age_days_at_decision`, `word_count`, `has_word_count`, `content_type` (one-hot), `main_intent` (one-hot) |
| Keyword context | `search_volume`, `competition`, `cpc`, `has_keyword_data` |

**Missing-value handling.** Missingness follows `content_type` (one type has no keyword data at
all), so a blind `fillna(0)` would silently encode content type. Flags first (`has_word_count`,
`has_keyword_data`), then fill.

---

## 5. Evaluation

**Split.** `GroupKFold(5)` grouped by `client_id`; **every metric is out-of-fold**. Pages from one
client share hidden character (same site, same editorial team), so a random split lets the model
memorise the client and fake skill.

**The comparison table (same data, same split, same metrics):**

| Method | Base rate | P@20 | P@50 | P@200 | Lift@50 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|---|---|
| Random ordering | 0.616 | 0.700 | 0.580 | 0.635 | 0.94 | 0.6169 | 0.4980 |
| Week-4 rule (contaminated) | 0.616 | 0.850 | 0.720 | 0.615 | 1.17 | 0.6159 | 0.5004 |
| Legal rule baseline | 0.616 | 0.900 | 0.740 | 0.730 | 1.20 | 0.6676 | 0.5621 |
| **Logistic regression (shipped)** | 0.616 | **0.900** | **0.880** | **0.815** | **1.43** | **0.7183** | **0.6406** |
| Random forest | 0.616 | 0.750 | 0.800 | 0.790 | 1.30 | 0.7108 | 0.6366 |
| *[leaky] RF + window-overlapping columns* | 0.616 | *1.000* | *1.000* | *0.995* | *1.62* | *0.7749* | *0.6865* |

**Split-design gap.** Random row split PR-AUC 0.7604 vs grouped out-of-fold 0.7183 — **+0.0421 of
the score was client memorisation**, not transferable skill.

**Stability.** Across 5 different client holdouts (seeds 42, 7, 2024, 101, 777):
PR-AUC 0.6678 ± 0.0258 (range 0.630–0.702), precision@50 0.816 ± 0.048. With only 30 clients, the
range is the result — not the single 0.7183.

**Risk deciles (out-of-fold).** Top decile 75.9% declined vs bottom decile 42.7% — a 1.78× spread:
real signal, no sharp boundary.

**Error analysis.**
- The Week-4 rule scores only **12 of 18,010 pages** above zero (11 of them declined). For the other
  17,998 everything ties at zero, so its ordering is arbitrary — hence ROC-AUC 0.500 and
  precision@200 falling back to the base rate. It is a decent *filter* and not a *ranker*.
- The model's own weak spot is the middle of the queue: deciles 5–7 sit at 62–71%, barely above the
  61.6% base rate. Honest reading: the queue is trustworthy at the top and near-uninformative in the
  middle.
- 14 of the top 200 carry only `model_pattern_only` — the model ranks them high but no human-readable
  rule matches. Those are downgraded to `monitor` by design.

**Leakage tests run (all in `w06_validation_audit.ipynb`).**
1. Deliberate leak: adding `trend_pct` → ROC-AUC 0.9997. The harness works.
2. Train-with / train-without on the window-overlapping group → precision@200 0.995 vs 0.790.
3. Product-flag and ID scan of the final feature set → clean (exact-name matching; my first version
   of this check used substring matching and produced false positives on the legal `prior_*_trend`
   columns).

---

## 6. Interpretation

**What the model leans on** (permutation importance, out-of-fold, drop in PR-AUC when shuffled):

| Feature | Importance | Standardised coefficient | Reading (observed, directional) |
|---|---|---|---|
| `log_clicks_prev30` | 0.0773 | −0.583 | Pages that convert impressions into clicks are associated with lower decline risk |
| `content_age_days_at_decision` | 0.0423 | −0.395 | In this slice older pages declined *less*, not more |
| `log_impr_first30` | 0.0400 | −0.445 | Sustained earlier demand is associated with stability |
| `log_sessions_prev30` | 0.0234 | −0.177 | Site-side engagement points the same way as clicks |
| `log_impr_prev30` | 0.0208 | **+0.910** | Holding clicks fixed, a recent impression spike is associated with higher decline risk |
| `prior_impr_trend_pct` | 0.0136 | +0.229 | Momentum already visible before the decision point carries forward |

**The single readable pattern:** *an impression spike that did not turn into clicks* is the strongest
decision-time warning sign in this slice — impressions up (+0.910) with clicks down (−0.583). These
traffic columns are correlated with each other, so the coefficients are a direction reading, not
isolated effects.

**Surprises and negative results.**
- **Word count is mixed grouped, and does not survive in the model.** The March 2026 FlyRank paper
  observed growing pages at 3.2K words vs declining pages at 2.3K (+37.6%). Grouped here, the
  1,000–2,000-word band does decline more (79.4%, n=1,444, lift 1.29) — but the two label groups
  average 3,483 vs 3,432 words (1.5%, n=12,785), the `<1000` bucket holds only 15 pages and must not
  be read, and permutation importance is ≈ 0.0009. Not a contradiction of the paper — that measures
  an observed state, this measures predictive power once demand and click signals are present.
- **Low click-through at high exposure is the strongest hand-checkable signal.** Among pages with
  ≥500 impressions, decline runs monotonically from 73.6% (lowest prior-CTR quartile) to 48.9%
  (highest), a 24.7-point spread on ~2,780 pages per quartile.
- **A spike is not good news.** Decline risk falls as prior momentum improves (70.6% → 52.4%) but
  turns back up to 58.7% for pages that gained more than +50% — mean reversion, and the reason the
  model's impressions coefficient is positive.
- **Content age points the "wrong" way.** Older content in this slice declined less
  (365+ tier: 44.9% vs 91–180 tier: 71.2%). Observational and confounded (age correlates with
  content mix and demand level) — reported as a directional observation, not a recommendation to
  let content age.
- **My own baseline failed.** The most useful result of the project is that the rule I built in
  Week 4 cannot rank.

---

## 7. Recommendation

Ranked actions an editor could use tomorrow (each with the evidence behind it and what would make
it wrong):

1. **Work the model queue instead of an age/freshness sort — start with the top 50.**
   *Evidence:* precision@50 0.88 vs 0.74 (legal rule) and 0.616 (base rate) — roughly 44 of the
   first 50 hours land on real decliners instead of 31. *Wrong if:* the portfolio changes shape, or
   the period sits inside a strong seasonal swing.
2. **Use "old + high impressions" as a filter, never as a ranker.**
   *Evidence:* it scores 12 of 18,010 pages above zero (11 declined) and is silent on the rest;
   ROC-AUC 0.500. *Wrong if:* on the full warehouse, `days_since_last_update` can be re-aligned to a
   proper decision point and regains power.
3. **Treat "impressions spiking without clicks" as the early-warning signal.**
   *Evidence:* top permutation importance (`log_clicks_prev30`, 0.077) with opposite-signed
   coefficients on impressions (+0.910) and clicks (−0.583); grouped, the lowest prior-CTR quartile at
   ≥500 impressions declined at 73.6% vs 48.9% in the highest. *Wrong if:* the page deliberately serves
   an on-SERP informational need, where low CTR is normal.
4. **Split the work by reason code instead of calling everything "refresh".**
   *Evidence:* of the top 200 — 97 `review_for_refresh`, 62 `review_metadata_and_intent`
   (clicks falling while impressions hold: a title/meta job, not a rewrite), 27 `protect_and_refresh`,
   14 `monitor`. *Wrong if:* the thresholds behind the reason codes move — they are policy choices.
5. **Keep a human gate in front of every action; automate nothing.**
   *Evidence:* the model never reads page content, cannot see a sibling page absorbing demand
   (consolidation), and cannot separate seasonality from decline. This is a design boundary, not a
   tunable parameter.

### The four states the lane asks for

The card asks the engine to score pages that are **growing, declining, recovering, or worth review**.
Those states sit on opposite sides of the decision point, so the queue carries them in two columns
and never mixes them:

| Column | Built from | What it is for |
|---|---|---|
| `decision_state` | prior window only — `slipping` / `steady` / `spiking` | **Actionable.** Visible to an editor at the decision point. Top 200: 124 slipping, 41 steady, 35 spiking |
| `outcome_state` | outcome window — `declining` / `recovering` / `growing` / `stable` | **Reporting and evaluation only.** Label-side information: never a feature, never predicted |

Two reason codes cover the growth side: `growing_with_demand` (prior window up >20% with ≥500
impressions) and `spiking_may_revert` (prior window up >50% — the signal audit measured that bucket
declining at 58.7%, above the 52.4% trough, so a jump is not by itself good news). Both map to a new
action, `protect_and_watch` (2,344 pages across the queue).

**What the top of the queue actually contained:**

| Slice | declining | recovering | growing | stable |
|---|---|---|---|---|
| Top 50 | 88% | 6% | 4% | 2% |
| Top 200 | 82% | 5% | 4% | 10% |
| Top 1,000 | 77% | 6% | 3% | 14% |
| *Whole population* | *62%* | *6%* | *7%* | *25%* |

Read the top row against the last: the queue concentrates decline (62% → 88%) and pushes growth out
(7% → 4%). It is not merely surfacing large pages.

**Recovery can be reported, not predicted.** Detecting a recovery *before* it happens needs two
consecutive deltas — a fall, then a rise. This slice exposes only two pre-decision windows, i.e. one
delta. So the engine can say that 1,063 pages recovered; it cannot say in advance which ones will.
That is a data-shape limit, not a modelling failure — the warehouse's daily table would lift it.

**Confidence.** Medium at the top of the queue (precision@50 stable at 0.816 ± 0.048 across client
holdouts), low in the middle (deciles 5–7 sit near the base rate), and out of scope below the
100-impression floor.

---

## 8. Reproducibility

From a fresh clone:

```bash
git clone https://github.com/tu-h-nguyn/FlyRank-End-to-End-Machine-Learning-Project-Internship
cd FlyRank-End-to-End-Machine-Learning-Project-Internship
pip install -r requirements.txt
python work/scripts/capstone_pipeline.py      # ~25s; writes work/outputs/*.json + work/figures/*.svg
```

Then run the notebooks top to bottom (Colab badges in `work/README.md`, or locally with Jupyter):
`w06_validation_audit.ipynb` → `w07_action_playbook.ipynb` → `capstone.ipynb`.

- **Seed:** `RANDOM_SEED = 42` everywhere (splits, models, permutation importance).
- **CV:** `GroupKFold(5)` by `client_id` — deterministic, no seed dependence.
- **Environment:** Python 3.11, pandas 2.x, scikit-learn 1.7.x, matplotlib 3.x (`requirements.txt`).
  Random-forest numbers can move a point or two between scikit-learn versions; the shipped logistic
  regression is stable.
- **Receipts (committed):** `work/outputs/capstone_metrics.json` (every metric, base rate, split
  design, full exclusion list), `capstone_importance.json`, `capstone_coefficients.json`,
  `capstone_queue_top20.json`, `capstone_queue_summary.json`, `monitoring_thresholds.json`.
- **Not committed by design:** `work/outputs/refresh_action_queue.csv` (18,010 rows) — repo policy
  blocks dataset CSVs. It is regenerated by the single command above.
- **No sealed-holdout claim is made.** Every number here is out-of-fold cross-validation on one
  snapshot; the honest phrase is "out-of-fold, grouped by client", not "blind test".

---

## 9. Acknowledgments & data credit

Built on the **FlyRank ML Internship dataset** — <https://flyrank.ai>. Real, anonymized search and
content performance data made available for this internship. The March 2026 FlyRank research paper
(`docs/flyrank-seo-research-march-2026.pdf`) is the reference point audited in
`w06_validation_audit.ipynb`; the questions raised there are methodological, not corrections.

---

### Claims checklist

- Every conclusion uses observed / measured / associated with / decision-support language.
- Base rate (0.6155) is printed next to every precision@K and accuracy figure in this report.
- No causal claim appears anywhere: this work cannot say a refresh recovers traffic.
- No claim about Google's algorithm, AI citations, or AI rankings.
- No client-identifying details anywhere in `work/`.
- Numbers in this report match a fresh re-run of `work/scripts/capstone_pipeline.py` (seed 42).
