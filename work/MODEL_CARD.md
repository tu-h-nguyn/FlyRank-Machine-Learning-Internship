# Model card — 30-Day Decline Queue

A one-page summary of what this model is, what it is for, and where it breaks. Every number
below is read from a committed receipt in `work/outputs/` and checked against it by
`tests/test_capstone.py`.

| | |
|---|---|
| **Model** | Logistic regression (standardised inputs, L2, `max_iter=2000`), scikit-learn |
| **Version** | Capstone run, seed 42 — `work/scripts/capstone_pipeline.py` |
| **Owner** | John (FlyRank ML Internship, Lane 2 — Refresh / Content Opportunity Scoring) |
| **Output** | A risk score in [0, 1] per page, plus reason codes, a suggested action and a confidence label |
| **Receipts** | `capstone_metrics.json`, `evidence_audit.json`, `capstone_coefficients.json` |

## Intended use

- **Ordering a human review queue.** An editor with capacity for ~50 pages a week opens the queue
  from the top and reviews each page before acting.
- **Unit:** one pseudonymous content item at one decision point (the start of a 30-day window).
- **Question answered:** *which pages are most likely to lose more than 20% of their search
  impressions over the next 30 days?*

## Out of scope — do not use it for

- **Automatic changes** to any page. There is a human gate in front of every action by design.
- **Causal claims.** The model ranks *associated* risk. It cannot say that refreshing a page will
  recover its traffic; there is no experiment behind it.
- **Pages below 100 prior-window impressions.** They were filtered out; the model has not been
  evaluated on them.
- **Predicting recovery.** That needs two consecutive deltas; this data has one.
- **Anything about Google's ranking algorithm.**

## Training data

The public anonymized FlyRank starter slice: 30,000 pages × 44 columns, 32 pseudonymous clients,
one trailing 90-day snapshot. The 90-day totals split exactly into three 30-day windows. Features
come from the first two windows only; the label comes from the third. After the demand floor:
**18,010 pages across 30 clients, base rate 61.6%.** One client holds 31.6% of the pages.

**24 features**, all knowable at the decision point: demand level and momentum between the two
visible windows, prior click-through and its shift, sessions per impression, content age at the
decision point, word count with a measured flag, keyword context with a measured flag, content
type and intent. **Excluded:** the label sources (`trend_pct`, `trend_direction`), every
window-spanning 90-day total and rate, `days_since_last_update` (68% of pages were updated
inside the outcome window), product tiers, and the pseudonymous IDs.

## Performance

Out-of-fold under `GroupKFold(5)` by client. Intervals are 95% client-clustered bootstrap
intervals from 1,000 resamples of the 30 clients.

| Metric | Model | Rule baseline | Gap, model − rule |
|---|---|---|---|
| Precision@50 | 0.88 [0.70, 0.96] | 0.74 [0.54, 0.96] | +0.14 [−0.06, +0.24] |
| Precision@200 | 0.815 [0.725, 0.875] | 0.730 [0.625, 0.860] | +0.085 [−0.05, +0.17] |
| PR-AUC | 0.718 [0.660, 0.799] | 0.668 [0.578, 0.796] | +0.051 [−0.004, +0.086] |
| ROC-AUC | 0.641 [0.590, 0.660] | 0.562 [0.521, 0.595] | +0.079 [+0.004, +0.118] |

**How to read this.** The model's advantage over the rule is real across the whole ranking —
ROC-AUC's interval excludes zero, 96% of resamples favour it on PR-AUC, a whole-pipeline
permutation test puts chance at p = 0.005 (the smallest value 200 permutations can give), and it
beats the rule *inside* 14 of 18 clients large enough to test (sign test p = 0.015). The
precision@50 gap on its own is **not** secure: with 30 clients, the model's own top-50
precision could plausibly sit anywhere from 0.70 to 0.96, and the gap's interval crosses
zero. Quote "44 of the top 50 declined" as a point estimate, never as a guarantee.

**Complexity did not earn its keep.** A regularised gradient-boosted model (PR-AUC 0.697) and a
random forest (0.711) both land within noise of — and below — the logistic regression. The
readable model ships.

## Calibration — read the score as a rank

Brier skill score +0.052 over always predicting the base rate; expected calibration error 0.028;
calibration slope 0.78 (below 1: the scores are more extreme than the outcomes). The middle of the
range is well calibrated. At the top it overstates: the riskiest tenth averages a predicted 0.84
but 0.76 actually declined. The confidence labels behave as ordered — **high** 77.7% declined
(1,610 pages), **medium** 68.7% (9,319), **low** 48.5% (7,081) — but "high" means roughly
three in four, not "certain".

## Robustness

- **Other definitions.** Across 4 demand floors × 3 decline thresholds, the model beats the rule on
  PR-AUC in 12 of 12 settings; on precision@50 it wins 9, ties 2 and loses 1 (the loosest label,
  −10%, with the lowest floor).
- **Without the largest client** (31.6% of pages): PR-AUC 0.740 vs 0.714 for the rule. **Inside
  that client alone:** 0.635 vs 0.549. The result is not one client's artefact.
- **Split design.** A random row split inflates PR-AUC by +0.042 through client memorisation.

## Known failure modes

1. **The middle of the queue is near the base rate** (deciles 5–7 at 62–71%). Trust the top.
2. **No content understanding.** It cannot see a sibling page absorbing demand, seasonality, or
   what the page says.
3. **Impression spikes.** Pages whose impressions jumped more than +50% declined more often
   (58.7%) than pages up 20–50% (52.4%); `spiking_may_revert` flags them so a reviewer does not
   read a spike as good news.
4. **Client mix.** Two of 18 testable clients have a within-client ROC-AUC below 0.5 — for them
   the ordering is no better than chance.

## Monitoring and retraining

`work/outputs/monitoring_thresholds.json` records the alert bands: base rate outside
0.52–0.72, precision@50 below the rule baseline's 0.74, any key feature median drifting more
than 20%, or the population moving more than 25%. Retrain monthly or on any alert, and re-run
the leakage checklist (`w06_validation_audit.ipynb`) and `pytest tests/` before trusting a
new number.

## Ethics and data safety

Only pseudonymous IDs and aggregates leave the repo. No client names, domains, URLs, titles or
queries appear in any output; the per-client figures are published by size rank, never by ID.
The model supports the order of human review and nothing else.
