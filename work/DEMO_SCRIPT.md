# Demo Script — 3-5 Minute Live Run

Record this as a screen recording with narration. No slides — the real thing running.

---

## Before you start

- Open a terminal in the repo root
- Have the capstone notebook ready in Colab or Jupyter
- Have the deployed paper open in a browser tab

---

## 0:00–0:30 — Intro (what and for whom)

**Show:** The README on GitHub.

**Say:** "This is a content refresh priority engine. It takes a portfolio of 18,000 web pages and ranks them by their risk of losing search traffic, so an editorial team that can only review 50 pages a week knows which ones to look at first. It's built on real, anonymized FlyRank search data."

---

## 0:30–1:30 — Live pipeline run

**Run in terminal:**

```bash
python work/scripts/capstone_pipeline.py
```

**While it runs (~25 seconds), narrate:**

"This is the whole pipeline running end to end. It loads the anonymized CSV — 30,000 pages across 32 clients. First it decomposes the 90-day window into three 30-day sub-windows and keeps only the two that precede the outcome period. Then it builds 24 features, trains a logistic regression with a client-grouped 5-fold split, and writes the metrics and figures."

**When it finishes, show the terminal output briefly.**

---

## 1:30–2:30 — Results walkthrough

**Show:** Open `work/outputs/capstone_metrics.json` or the evaluation table in the capstone notebook.

**Say:** "Here are the results. The shipped model — logistic regression — puts 88% real decliners in the top 50, compared to 74% for the hand-written rule and 62% by chance. That's roughly 44 out of 50 useful reviews instead of 31."

**Show:** The precision@K chart (`work/figures/precision_at_k.svg`).

**Say:** "This chart shows precision at different queue depths. The blue line is the model, the orange is the legal rule baseline, and the dashed line is the leaky model — the one that was allowed to see the outcome window. The gap between the blue and dashed lines is what honesty costs: precision@200 drops from 0.995 to 0.815. I kept the honest version."

---

## 2:30–3:30 — Design decision + limitation (on camera)

**Design decision — the window decomposition:**

**Show:** The window decomposition diagram in the capstone notebook or the architecture section of the README.

**Say:** "The most important design decision was the window decomposition. The 90-day totals in the dataset — impressions_90d, clicks_90d, the CTR — all span the outcome window. Using them is temporal leakage. I decomposed the 90-day window into first30, prev30, and last30, proved the decomposition is exact (reconstruction error = 0), and built all features from first30 and prev30 only. This is why the leaky model's 0.995 is a confession, not a result."

**Limitation — the middle of the queue:**

**Show:** The risk deciles chart (`work/figures/risk_deciles.svg`).

**Say:** "One real limitation: the model is useful at the top and bottom of the queue, but deciles 5 through 7 sit at 62-71%, barely above the 61.6% base rate. The middle of the queue is near-random. For a team reviewing 50 pages a week, that's fine — they'll never get to the middle. But if someone tried to use this for the whole portfolio, they'd be disappointed."

---

## 3:30–4:30 — The output in practice

**Show:** The action queue — either run a quick cell in the capstone notebook to display the top 20, or show `work/outputs/capstone_queue_top20.json`.

**Say:** "The actual deliverable is this ranked queue. Each row has a risk score, reason codes like 'review_for_refresh' or 'review_metadata_and_intent', a confidence label, and the decision-time state. An editor opens this, starts at the top, and applies their own judgment — is this page worth the hour? The model decides the order; the human decides the action."

---

## 4:30–5:00 — Wrap up

**Show:** The deployed paper at tu-h-nguyn.github.io/FlyRank-End-to-End-Machine-Learning-Project-Internship

**Say:** "The full write-up is deployed as a research paper here. Every number traces back to the JSON files in the repo, which are regenerated deterministically by the single command I ran at the start. The repo README has setup instructions, the full evaluation table, and the limitations list. Thanks for watching."

---

## Checklist before uploading

- [ ] Video is 3–5 minutes
- [ ] Shows a live `capstone_pipeline.py` run, not slides
- [ ] Explains one design decision (window decomposition) on camera
- [ ] Explains one limitation (uninformative middle of queue) on camera
- [ ] Clear narration throughout
- [ ] Deployed paper shown at the end
