# Content Refresh Priority Engine

**A machine-learning pipeline that ranks 18,000+ web pages by their risk of losing search traffic, so an editorial team knows which pages to review first.**

Built during the [FlyRank ML Internship](https://flyrank.ai) on real, anonymized search-console and analytics data. The output is a ranked action queue — not an automatic decision, but a prioritized list with reason codes that supports human editorial review.

---

## Who this is for

- **Content editors** managing large portfolios who can review ~50 pages a week and need to pick the right ones first.
- **SEO practitioners** who want a data-driven triage instead of sorting by "oldest" or "most traffic."
- **ML learners** who want to see a complete, honest pipeline: problem framing → leakage hunting → baseline → model → evaluation → actionable output.

---

## What it does

Given a snapshot of search and content performance data (impressions, clicks, sessions, content age, keyword metrics), the engine:

1. **Decomposes the 90-day window** into three 30-day sub-windows and uses only the two that precede the outcome period — no future information leaks into the features.
2. **Builds 24 decision-time features** from demand levels, prior momentum, click capture rates, content metadata, and keyword context.
3. **Trains a logistic regression** scored out-of-fold under a client-grouped 5-fold split, so no client's pages appear in both train and test.
4. **Produces a ranked queue** of 18,010 pages, each carrying a risk score, reason codes, a suggested action (`review_for_refresh`, `review_metadata_and_intent`, `protect_and_refresh`, `monitor`), and a confidence label.

---

## Setup — from zero to results

### Option A: Google Colab (zero install, recommended)

Click any badge below to open the notebook directly:

| Notebook | What it does | Open |
|---|---|---|
| `01_first_look_and_discovery` | Explore the dataset, find your first real pattern | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/tu-h-nguyn/FlyRank-End-to-End-Machine-Learning-Project-Internship/blob/main/notebooks/01_first_look_and_discovery.ipynb?flush_cache=true) |
| `02_your_first_readable_model` | Build a transparent rule-based model | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/tu-h-nguyn/FlyRank-End-to-End-Machine-Learning-Project-Internship/blob/main/notebooks/02_your_first_readable_model.ipynb?flush_cache=true) |
| `capstone` | Full capstone: leakage-free pipeline end to end | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/tu-h-nguyn/FlyRank-End-to-End-Machine-Learning-Project-Internship/blob/main/work/notebooks/capstone.ipynb?flush_cache=true) |

### Option B: Local

```bash
git clone https://github.com/tu-h-nguyn/FlyRank-End-to-End-Machine-Learning-Project-Internship.git
cd FlyRank-End-to-End-Machine-Learning-Project-Internship
pip install -r requirements.txt

# Run the reference pipeline (~10s on the bundled 30k-row sample)
python scripts/run_all.py

# Run the capstone pipeline (~25s, writes metrics + figures)
python work/scripts/capstone_pipeline.py
```

**Requirements:** Python 3.11+, and the packages in `requirements.txt`:

```
pandas>=2.2
numpy>=1.26
scikit-learn>=1.4
matplotlib>=3.8
reportlab>=4.0
duckdb>=1.0
huggingface_hub>=0.24
```

### Option C: Full warehouse (79M rows, optional)

The full dataset is hosted at [`FlyRank/internship-warehouse`](https://huggingface.co/datasets/FlyRank/internship-warehouse) (gated — request access and accept the data-use terms; approval is instant). Query it via DuckDB without downloading:

```python
import duckdb
con = duckdb.connect()
con.sql("SELECT count(*) FROM 'hf://datasets/FlyRank/internship-warehouse/warehouse.parquet'")
```

See `notebooks/03_working_with_the_full_release.ipynb` for the guided walkthrough.

---

## Architecture

```
data/raw/content_refresh_anonymized.csv          30,000 pages × 44 columns
        │
        │  Window decomposition + leakage exclusion
        │  (90d → first30 + prev30 + last30; only first30/prev30 used)
        ▼
   24 decision-time features
        │
        ├─── Rule baseline (hand-written, no fitting)
        │         └─ "demand fell between visible windows + still has traffic"
        │
        └─── Logistic regression (standardised, GroupKFold by client_id)
                  │
                  ▼
         Ranked action queue (18,010 rows)
         ┌────────────────────────────────────────────┐
         │  risk_score · reason_codes · suggested_action │
         │  confidence_label · decision_state            │
         └────────────────────────────────────────────┘
                  │
                  ▼
         Human editorial review
         (the model supports the order, not the decision)
```

**Key design choice:** The 90-day metrics window overlaps the outcome period. Instead of using the convenient `impressions_90d` or `days_since_last_update`, every feature is built from the two sub-windows that precede the label window. This costs performance (precision@200 drops from 0.995 to 0.815) but removes temporal leakage — the model cannot cheat by seeing the future.

---

## Evaluation results (v2 — leakage-free)

All metrics are **out-of-fold** under `GroupKFold(5)` grouped by `client_id`. Base rate = 61.6%.

| Method | P@20 | P@50 | P@200 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|
| Random ordering | 0.700 | 0.580 | 0.635 | 0.617 | 0.498 |
| Week-4 rule (contaminated) | 0.850 | 0.720 | 0.615 | 0.616 | 0.500 |
| Legal rule baseline | 0.900 | 0.740 | 0.730 | 0.668 | 0.562 |
| **Logistic regression (shipped)** | **0.900** | **0.880** | **0.815** | **0.718** | **0.641** |
| Random forest | 0.750 | 0.800 | 0.790 | 0.711 | 0.637 |
| *[leaky] RF + overlapping columns* | *1.000* | *1.000* | *0.995* | *0.775* | *0.687* |

**What this means:** At the team's capacity of ~50 pages/week, roughly **44 of the first 50** are real decliners (vs 31 for the hand-written rule and 29 by chance).

**Stability:** Across 5 different client holdouts (seeds 42, 7, 2024, 101, 777): PR-AUC 0.668 ± 0.026, precision@50 0.816 ± 0.048.

**Split-design gap:** Random row split PR-AUC = 0.760 vs grouped = 0.718. The +0.042 difference was client memorisation, not transferable skill.

---

## Limitations

1. **One snapshot, no causal claims.** This is cross-sectional data from one time period. The model ranks pages by *associated* risk — it cannot say refreshing a page will recover its traffic. The honest framing is decision-support, not prediction.

2. **Small client pool (30 clients).** With only 30 clients in the grouped split, the PR-AUC range across holdouts (0.630–0.702) is wide. The range is the result, not the single 0.718.

3. **The middle of the queue is uninformative.** Risk deciles 5–7 sit at 62–71% decline rate, barely above the 61.6% base rate. The queue is trustworthy at the top and near-random in the middle.

4. **No content understanding.** The model never reads page content, cannot detect sibling pages absorbing demand (consolidation), and cannot separate seasonality from genuine decline. A human gate in front of every action is a design requirement, not a nice-to-have.

5. **Recovery cannot be predicted ahead of time.** Detecting a recovery before it happens needs two consecutive deltas (a fall, then a rise). This slice has only one pre-decision delta. The engine can report that 1,063 pages recovered; it cannot say in advance which ones will.

6. **The bundled dataset only.** The full ~79M-row warehouse was not used (no `HF_TOKEN` in the build environment). The feature contract is source-agnostic, but the published numbers are from the 30k public slice.

7. **`days_since_last_update` was excluded.** It is exactly the signal my Week-4 rule depended on, but 68% of pages were updated inside the outcome window — it knows the future. This was the hardest exclusion and the most important one.

---

## Key findings

- **"Impressions spiking without clicks" is the strongest early-warning signal.** The logistic model's largest positive coefficient is on `log_impr_prev30` (+0.910) while `log_clicks_prev30` is the most important feature (importance 0.077, coefficient −0.583). Translation: traffic showing up without engagement is a warning, not good news.

- **My own Week-4 baseline failed.** It scored only 12 of 18,010 pages above zero. It works as a filter ("find old, visible pages") but cannot order a queue — ROC-AUC 0.500. This was the most useful result of the project.

- **Older content declined less, not more.** In this slice, pages older than 365 days declined at 44.9% vs 71.2% for 91–180 day pages. Confounded with content mix and demand — reported as directional, not a recommendation.

---

## Repository structure

| Path | What it is |
|---|---|
| `data/raw/` | The anonymized starter dataset (30k pages × 44 columns) |
| `scripts/` | Reference pipeline: prepare → baseline → train → evaluate → PDF |
| `notebooks/` | Week 1–2 guided notebooks (Colab-ready) |
| `work/notebooks/` | All assignment notebooks (ML-02 through ML-12) |
| `work/scripts/` | Capstone pipeline + paper builder |
| `work/outputs/` | Metrics JSONs (committed receipts) |
| `work/figures/` | SVG charts from the capstone pipeline |
| `work/capstone_report.md` | Full capstone write-up |
| `docs/index.html` | Deployed research paper |
| `docs/portfolio/` | Personal portfolio site |
| `outputs/` | Reference pipeline outputs (model report, sample queue, charts) |
| `skills/` | AI assistant instruction library |

---

## Deployed outputs

- **Research paper:** [tu-h-nguyn.github.io/FlyRank-End-to-End-Machine-Learning-Project-Internship](https://tu-h-nguyn.github.io/FlyRank-End-to-End-Machine-Learning-Project-Internship/)
- **Portfolio site:** [tu-h-nguyn.github.io/FlyRank-End-to-End-Machine-Learning-Project-Internship/portfolio](https://tu-h-nguyn.github.io/FlyRank-End-to-End-Machine-Learning-Project-Internship/portfolio/)
- **FEM wave equation write-up** (separate repo): [https://tu-h-nguyn.github.io/fem-wave-1d/](https://tu-h-nguyn.github.io/fem-wave-1d/) — sharp CFL analysis, every table machine-verified ([code](https://github.com/tu-h-nguyn/fem-wave-1d))

---

## AI transparency

This project was built with Claude (Anthropic) as an AI coding assistant. Specifically:

- **Pipeline code** (`work/scripts/capstone_pipeline.py`, `work/scripts/build_paper.py`): scaffolded with Claude, then reviewed and modified by me. Every function was tested against the data to verify it produces correct outputs.
- **Feature engineering and leakage analysis**: the window decomposition logic and feature exclusion list were my design decisions, validated by running deliberate-leak tests in the notebooks.
- **Report and paper writing**: drafted with Claude's help, but every claim was checked against the actual metrics JSONs (`work/outputs/*.json`), and the claims checklist at the end of `capstone_report.md` was verified manually.
- **What I checked myself**: the leakage exclusion list (especially the `days_since_last_update` decision), the grouped-split design, the stability analysis across seeds, and every number in the evaluation table against a fresh pipeline run.

---

## Reproducibility

```bash
git clone https://github.com/tu-h-nguyn/FlyRank-End-to-End-Machine-Learning-Project-Internship.git
cd FlyRank-End-to-End-Machine-Learning-Project-Internship
pip install -r requirements.txt
python work/scripts/capstone_pipeline.py   # ~25s; writes work/outputs/*.json + work/figures/*.svg
```

- **Seed:** `RANDOM_SEED = 42` everywhere.
- **CV:** `GroupKFold(5)` by `client_id` — deterministic, no seed dependence.
- **Environment:** Python 3.11, pandas 2.x, scikit-learn 1.7.x, matplotlib 3.x.

---

## Data safety

Only the anonymized CSV ships in this repo — no client names, domains, URLs, titles, or keywords. See [DATA_USE.md](DATA_USE.md) for the full data-use terms. The `.gitignore` blocks datasets by default, and CI fails any commit that includes one.

---

*Built on the [FlyRank ML Internship dataset](https://flyrank.ai). Code under MIT ([LICENSE](LICENSE)); data under [DATA_USE.md](DATA_USE.md).*
