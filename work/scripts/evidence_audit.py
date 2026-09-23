"""
Evidence audit — is the capstone's win bigger than the noise?

`capstone_pipeline.py` reports point estimates: precision@50 of 0.88 against 0.74 for the
rule, PR-AUC 0.718 against 0.668. With 30 clients, one of which holds almost a third of the
pages, a point estimate is not enough. This script attacks the headline six ways and writes
every answer to a committed receipt:

    1. Client-clustered bootstrap   95% intervals for every headline metric and for the
                                    paired gap model - baseline (clients resampled, not rows)
    2. Permutation test             retrain the whole pipeline on shuffled labels; how often
                                    does chance match the real PR-AUC?
    3. Complexity check             gradient boosting as a challenger: does it earn its keep?
    4. Calibration                  can the risk score be read as a probability?
    5. Per-client view              does the model beat the rule inside each client, or only
                                    in the pooled ranking?
    6. Sensitivity                  do the conclusions survive other demand floors, other
                                    decline thresholds, and dropping the largest client?

Run from the repo root, after (or without) the main pipeline:

    python work/scripts/evidence_audit.py

Outputs (committed receipts):
    work/outputs/evidence_audit.json
    work/figures/evidence_*.svg

Seeds are fixed (RANDOM_SEED = 42). Runtime is two to three minutes on a laptop, most of it
the 400 retrained pipelines of the permutation test.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capstone_pipeline as cp  # noqa: E402  (the single source of the feature contract)

RANDOM_SEED = cp.RANDOM_SEED
N_BOOT = 1000
N_PERM = 200
CAPACITY_K = [10, 20, 30, 50, 75, 100, 150, 200, 300, 500]
HEADLINE_K = [20, 50, 200]
MIN_CLIENT_PAGES = 50       # per-client view: below this a within-client AUC is noise
MIN_CLIENT_CLASS = 10       # ... and each class needs at least this many pages
FLOORS = [50, 100, 250, 500]
THRESHOLDS = [-10.0, -20.0, -30.0]

OUT = cp.OUT
FIG = cp.FIG


# --------------------------------------------------------------------------------------
# Scores — every model scored out-of-fold under the pipeline's own GroupKFold(5)
# --------------------------------------------------------------------------------------

def make_hgb() -> HistGradientBoostingClassifier:
    """A regularised, deliberately reasonable challenger — not a strawman."""
    return HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=100,
        l2_regularization=1.0, random_state=RANDOM_SEED,
    )


def oof_hgb(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    oof = np.zeros(len(y), dtype=float)
    for tr, te in GroupKFold(n_splits=cp.N_SPLITS).split(X, y, groups):
        oof[te] = make_hgb().fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    return oof


def hits_at(scores: np.ndarray, labels: np.ndarray, ks: list[int]) -> np.ndarray:
    """Decliners caught in the top k, for every k at once (one sort, one cumsum).
    Ties break in row order — identical to cp.precision_at_k."""
    order = np.argsort(-scores, kind="stable")
    csum = np.cumsum(labels[order])
    return np.array([csum[min(k, len(csum)) - 1] for k in ks], dtype=float)


def metric_row(scores: np.ndarray, labels: np.ndarray) -> dict:
    hits = hits_at(scores, labels, HEADLINE_K)
    row = {f"p@{k}": h / k for k, h in zip(HEADLINE_K, hits)}
    row["pr_auc"] = float(average_precision_score(labels, scores))
    row["roc_auc"] = float(roc_auc_score(labels, scores))
    return row


# --------------------------------------------------------------------------------------
# 1. Client-clustered bootstrap
# --------------------------------------------------------------------------------------

def clustered_bootstrap(scores: dict[str, np.ndarray], y: np.ndarray, groups: np.ndarray,
                        n_boot: int = N_BOOT) -> dict:
    """Resample CLIENTS with replacement. Pages inside a client are correlated, so resampling
    rows would pretend we have 18,010 independent observations when we have 30 clusters."""
    rng = np.random.default_rng(RANDOM_SEED)
    clients = np.unique(groups)
    members = [np.flatnonzero(groups == c) for c in clients]
    names = list(scores)
    metrics = ["p@20", "p@50", "p@200", "pr_auc", "roc_auc"]
    draws = {n: {m: np.empty(n_boot) for m in metrics} for n in names}
    capacity = {n: np.empty((n_boot, len(CAPACITY_K))) for n in names}
    base = np.empty(n_boot)

    for b in range(n_boot):
        idx = np.concatenate([members[i] for i in rng.integers(0, len(clients), len(clients))])
        yb = y[idx]
        base[b] = yb.mean()
        for n in names:
            sb = scores[n][idx]
            row = metric_row(sb, yb)
            for m in metrics:
                draws[n][m][b] = row[m]
            capacity[n][b] = hits_at(sb, yb, CAPACITY_K)

    def ci(a: np.ndarray) -> dict:
        lo, hi = np.percentile(a, [2.5, 97.5])
        return {"lo": round(float(lo), 4), "hi": round(float(hi), 4)}

    point = {n: metric_row(scores[n], y) for n in names}
    out = {
        "method": f"{n_boot} resamples of the {len(clients)} clients with replacement; "
                  "percentile 95% intervals; every model is scored on the SAME resample, so "
                  "gaps are paired",
        "base_rate_ci": ci(base),
        "intervals": {
            n: {m: {"point": round(point[n][m], 4), **ci(draws[n][m])} for m in metrics}
            for n in names
        },
        "paired_gaps": {},
        "capacity": {
            "k": CAPACITY_K,
            **{n: {"point": hits_at(scores[n], y, CAPACITY_K).astype(int).tolist(),
                   "lo": np.percentile(capacity[n], 2.5, axis=0).round(1).tolist(),
                   "hi": np.percentile(capacity[n], 97.5, axis=0).round(1).tolist()}
               for n in names},
        },
    }
    for a, b in [("logreg", "rule"), ("logreg", "random"), ("logreg", "hgb"), ("logreg", "rf")]:
        gap = {}
        for m in metrics:
            delta = draws[a][m] - draws[b][m]
            gap[m] = {
                "point": round(point[a][m] - point[b][m], 4),
                **ci(delta),
                # Share of resamples in which the challenger tied or won: a one-sided
                # bootstrap p-value for "the shipped model is better".
                "share_resamples_not_better": round(float(np.mean(delta <= 0)), 4),
            }
        out["paired_gaps"][f"{a}_minus_{b}"] = gap
    return out


# --------------------------------------------------------------------------------------
# 2. Permutation test — the whole pipeline, retrained on shuffled labels
# --------------------------------------------------------------------------------------

def permutation_test(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray,
                     observed: float, n_perm: int = N_PERM) -> dict:
    rng = np.random.default_rng(RANDOM_SEED)
    base = float(y.mean())

    def lift(labels: np.ndarray) -> float:
        return average_precision_score(labels, cp.oof_scores(X, labels, groups, "logreg")) / labels.mean()

    # Null A — global shuffle: features carry no information about the label at all.
    null_global = np.array([lift(rng.permutation(y)) for _ in range(n_perm)])
    # Null B — shuffle inside each client: keeps every client's own decline rate, so a model
    # that only learned "which client declines more" would still pass. The stricter null.
    by_client = [np.flatnonzero(groups == c) for c in np.unique(groups)]

    def shuffle_within() -> np.ndarray:
        yp = y.copy()
        for idx in by_client:
            yp[idx] = rng.permutation(y[idx])
        return yp

    null_within = np.array([lift(shuffle_within()) for _ in range(n_perm)])
    obs = observed / base

    def summary(null: np.ndarray) -> dict:
        return {
            "null_mean": round(float(null.mean()), 4),
            "null_p95": round(float(np.percentile(null, 95)), 4),
            "null_max": round(float(null.max()), 4),
            "p_value": round(float((1 + np.sum(null >= obs)) / (1 + len(null))), 4),
        }

    return {
        "statistic": "out-of-fold PR-AUC / base rate (lift), logistic regression, GroupKFold(5)",
        "n_permutations": n_perm,
        "observed_lift": round(obs, 4),
        "global_shuffle": summary(null_global),
        "within_client_shuffle": summary(null_within),
        "_null_global": null_global,        # stripped before writing; used by the chart
        "_null_within": null_within,
    }


# --------------------------------------------------------------------------------------
# 4. Calibration
# --------------------------------------------------------------------------------------

def confidence_check(p: np.ndarray, y: np.ndarray, impressions_prev30: np.ndarray) -> dict:
    """Does each confidence label the queue prints actually mean what it says?"""
    labels = np.array([cp.confidence_label(a, b) for a, b in zip(p, impressions_prev30)])
    return {
        lab: {"pages": int((labels == lab).sum()),
              "observed_decline_rate": round(float(y[labels == lab].mean()), 4),
              "mean_predicted": round(float(p[labels == lab].mean()), 4)}
        for lab in ("high", "medium", "low")
    }


def calibration(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> dict:
    base = float(y.mean())
    brier = float(brier_score_loss(y, p))
    brier_ref = base * (1 - base)                       # always predicting the base rate
    bins = pd.qcut(pd.Series(p).rank(method="first"), n_bins, labels=False).to_numpy()
    rel = []
    ece = 0.0
    for b in range(n_bins):
        m = bins == b
        mp, oy = float(p[m].mean()), float(y[m].mean())
        rel.append({"bin": b + 1, "n": int(m.sum()), "mean_predicted": round(mp, 4),
                    "observed_rate": round(oy, 4)})
        ece += m.mean() * abs(mp - oy)
    # Recalibration slope: regress the label on logit(p). 1.0 = perfectly spread;
    # < 1 = the scores are too extreme; > 1 = too timid.
    logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(logit.reshape(-1, 1), y)
    return {
        "brier": round(brier, 4),
        "brier_base_rate_only": round(brier_ref, 4),
        "brier_skill_score": round(1 - brier / brier_ref, 4),
        "expected_calibration_error": round(float(ece), 4),
        "calibration_slope": round(float(lr.coef_[0][0]), 3),
        "calibration_intercept": round(float(lr.intercept_[0]), 3),
        "score_range": [round(float(p.min()), 4), round(float(p.max()), 4)],
        "reliability": rel,
    }


# --------------------------------------------------------------------------------------
# 5. Per-client view
# --------------------------------------------------------------------------------------

def per_client(d: pd.DataFrame, scores: dict[str, np.ndarray], y: np.ndarray) -> dict:
    rows = []
    for c, idx in d.reset_index(drop=True).groupby("client_id").indices.items():
        yc = y[idx]
        n_pos, n = int(yc.sum()), len(idx)
        if n < MIN_CLIENT_PAGES or min(n_pos, n - n_pos) < MIN_CLIENT_CLASS:
            continue
        k = max(5, n // 10)                               # the client's own top 10%
        r = {"client": c, "n": n, "base_rate": round(float(yc.mean()), 4), "top_k": k}
        for name in ("logreg", "rule"):
            s = scores[name][idx]
            r[f"roc_{name}"] = round(float(roc_auc_score(yc, s)), 4)
            r[f"ptop_{name}"] = round(float(hits_at(s, yc, [k])[0] / k), 4)
        rows.append(r)
    rows.sort(key=lambda r: -r["n"])
    wins = sum(r["roc_logreg"] > r["roc_rule"] for r in rows)
    wins_top = sum(r["ptop_logreg"] > r["ptop_rule"] for r in rows)
    ties_top = sum(r["ptop_logreg"] == r["ptop_rule"] for r in rows)
    n = len(rows)
    w = np.array([r["n"] for r in rows], dtype=float)
    return {
        "eligibility": f">= {MIN_CLIENT_PAGES} pages and >= {MIN_CLIENT_CLASS} of each class",
        "clients_eligible": n,
        "pages_covered": int(w.sum()),
        "roc_auc_model_wins": wins,
        "roc_auc_sign_test_p": round(float(binomtest(wins, n, 0.5, alternative="greater").pvalue), 4),
        "top10pct_model_wins": wins_top,
        "top10pct_ties": ties_top,
        "median_roc_auc_model": round(float(np.median([r["roc_logreg"] for r in rows])), 4),
        "median_roc_auc_rule": round(float(np.median([r["roc_rule"] for r in rows])), 4),
        "clients_where_model_roc_below_0_5": sum(r["roc_logreg"] < 0.5 for r in rows),
        # Client IDs are pseudonyms, but the per-client table is published by rank only.
        "clients": [{k: v for k, v in r.items() if k != "client"} | {"size_rank": i + 1}
                    for i, r in enumerate(rows)],
    }


# --------------------------------------------------------------------------------------
# 6. Sensitivity
# --------------------------------------------------------------------------------------

def sensitivity(frame: pd.DataFrame) -> dict:
    grid = []
    for floor in FLOORS:
        for thr in THRESHOLDS:
            d = frame[frame["impressions_prev_30d"] >= floor].copy()
            y = (d["trend_pct"] < thr).astype(int).to_numpy()
            g = d["client_id"].to_numpy()
            X = cp.design_matrix(d)
            lr = cp.oof_scores(X, y, g, "logreg")
            rule = cp.baseline_legal_rule(d)
            base = float(y.mean())
            grid.append({
                "min_prev30_impressions": floor, "decline_threshold_pct": thr,
                "rows": int(len(d)), "base_rate": round(base, 4),
                "model_pr_auc_lift": round(average_precision_score(y, lr) / base, 3),
                "rule_pr_auc_lift": round(average_precision_score(y, rule) / base, 3),
                "model_p@50": round(cp.precision_at_k(lr, y, 50), 3),
                "rule_p@50": round(cp.precision_at_k(rule, y, 50), 3),
            })
    beats = sum(r["model_pr_auc_lift"] > r["rule_pr_auc_lift"] for r in grid)
    p50 = [np.sign(r["model_p@50"] - r["rule_p@50"]) for r in grid]
    return {
        "grid": grid,
        "model_beats_rule_on_pr_auc_in": f"{beats} of {len(grid)} settings",
        # Top-50 precision is the noisier statistic, so it is counted separately, losses included.
        "precision_at_50_model_wins_ties_losses": [int(sum(s > 0 for s in p50)),
                                                   int(sum(s == 0 for s in p50)),
                                                   int(sum(s < 0 for s in p50))],
    }


def largest_client(d: pd.DataFrame, scores: dict[str, np.ndarray], y: np.ndarray) -> dict:
    """One client holds ~a third of the pages. Does the pooled result stand without it?"""
    groups = d["client_id"].to_numpy()
    sizes = pd.Series(groups).value_counts()
    big = sizes.index[0]
    keep = groups != big
    out = {"largest_client_share_of_pages": round(float(sizes.iloc[0] / len(groups)), 4)}
    for label, m in [("without_largest_client", keep), ("largest_client_only", ~keep)]:
        out[label] = {"rows": int(m.sum()), "base_rate": round(float(y[m].mean()), 4)}
        for name in ("logreg", "rule"):
            row = metric_row(scores[name][m], y[m])
            out[label][name] = {k: round(v, 4) for k, v in row.items()}
    return out


# --------------------------------------------------------------------------------------
# Charts — same visual system as the capstone figures
# --------------------------------------------------------------------------------------

LABELS = {"logreg": "Logistic regression (shipped)", "rule": "Rule baseline",
          "hgb": "Gradient boosting", "rf": "Random forest", "random": "Random ordering"}


def chart_gaps(boot: dict) -> None:
    import matplotlib.pyplot as plt
    metrics = [("p@20", "Precision@20"), ("p@50", "Precision@50"), ("p@200", "Precision@200"),
               ("pr_auc", "PR-AUC"), ("roc_auc", "ROC-AUC")]
    series = [("logreg_minus_rule", "vs rule baseline", cp.ACCENT, -0.17),
              ("logreg_minus_hgb", "vs gradient boosting", cp.WARN, 0.0),
              ("logreg_minus_random", "vs random ordering", cp.MUTED, 0.17)]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for key, label, color, off in series:
        g = boot["paired_gaps"][key]
        for i, (m, _) in enumerate(metrics):
            y = len(metrics) - 1 - i + off
            ax.plot([g[m]["lo"], g[m]["hi"]], [y, y], color=color, lw=2.2, solid_capstyle="round")
            ax.plot(g[m]["point"], y, "o", color=color, ms=6, label=label if i == 0 else None)
    ax.axvline(0, color=cp.INK, lw=1)
    ax.set_yticks(range(len(metrics)))
    ax.set_yticklabels([name for _, name in metrics][::-1])
    cp._style(ax, "How much better is the shipped model? Paired gaps, 95% intervals",
              "shipped model minus comparator (right of zero = shipped model better)", "")
    ax.grid(axis="x", color=cp.GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    cp.save(fig, "evidence_bootstrap.svg")


def chart_capacity(boot: dict, base_rate: float) -> None:
    import matplotlib.pyplot as plt
    cap = boot["capacity"]
    k = np.array(cap["k"])
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    for name, color in [("rule", cp.WARN), ("logreg", cp.ACCENT)]:
        pt, lo, hi = (np.array(cap[name][x]) / k for x in ("point", "lo", "hi"))
        if name == "logreg":        # shaded band for the shipped model ...
            ax.fill_between(k, lo, hi, color=color, alpha=0.16, lw=0)
        else:                       # ... thin dashed edges for the rule, so neither hides
            ax.plot(k, lo, ls=":", color=color, lw=1.1)
            ax.plot(k, hi, ls=":", color=color, lw=1.1)
        ax.plot(k, pt, "-o", color=color, ms=4, lw=2, label=f"{LABELS[name]} (95% band)")
    ax.axhline(base_rate, color=cp.MUTED, ls="--", lw=1, label=f"base rate {base_rate:.3f}")
    ax.set_xscale("log")
    ax.set_xticks(k)
    ax.set_xticklabels([str(x) for x in k])
    ax.set_ylim(0.4, 1.02)
    cp._style(ax, "Share of the queue that really declined, with client-bootstrap bands",
              "pages reviewed (top K of the queue)", "precision@K")
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    cp.save(fig, "evidence_capacity.svg")


def chart_permutation(perm: dict) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    bins = np.linspace(0.95, max(perm["observed_lift"], perm["_null_within"].max()) + 0.02, 50)
    ax.hist(perm["_null_global"], bins=bins, color=cp.MUTED, alpha=0.55,
            label="labels shuffled across all pages")
    ax.hist(perm["_null_within"], bins=bins, color=cp.WARN, alpha=0.55,
            label="labels shuffled within each client")
    ax.axvline(perm["observed_lift"], color=cp.ACCENT, lw=2.4)
    ax.text(perm["observed_lift"], ax.get_ylim()[1] * 0.92, "  real labels", color=cp.ACCENT,
            fontsize=9, fontweight="bold", va="top")
    cp._style(ax, f"The pipeline retrained {perm['n_permutations']}× on shuffled labels never came close",
              "PR-AUC lift over base rate (out-of-fold)", "retrained pipelines")
    ax.legend(frameon=False, fontsize=8, loc="upper center")
    cp.save(fig, "evidence_permutation.svg")


def chart_calibration(cal: dict) -> None:
    import matplotlib.pyplot as plt
    rel = cal["reliability"]
    x = [r["mean_predicted"] for r in rel]
    yv = [r["observed_rate"] for r in rel]
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    ax.plot([0.3, 0.95], [0.3, 0.95], color=cp.MUTED, ls="--", lw=1, label="perfect calibration")
    ax.plot(x, yv, "-o", color=cp.ACCENT, lw=2, ms=6, label="shipped model, by score decile")
    ax.set_xlim(0.3, 0.95)
    ax.set_ylim(0.3, 0.95)
    ax.set_aspect("equal")
    cp._style(ax, "Risk score vs observed decline rate",
              "mean predicted risk in the decile", "share that actually declined")
    ax.grid(axis="x", color=cp.GRID, linewidth=0.8)
    ax.text(0.93, 0.33, f"Brier skill {cal['brier_skill_score']:+.3f}\n"
                        f"ECE {cal['expected_calibration_error']:.3f}\n"
                        f"slope {cal['calibration_slope']:.2f}",
            ha="right", va="bottom", fontsize=8.5, color=cp.INK)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    cp.save(fig, "evidence_calibration.svg")


def chart_per_client(pc: dict) -> None:
    import matplotlib.pyplot as plt
    rows = pc["clients"]
    fig, ax = plt.subplots(figsize=(7.2, 0.9 + 0.3 * len(rows)))
    for i, r in enumerate(rows):
        y = len(rows) - 1 - i
        better = r["roc_logreg"] >= r["roc_rule"]
        ax.plot([r["roc_rule"], r["roc_logreg"]], [y, y],
                color=cp.GOOD if better else cp.WARN, lw=2, alpha=0.7)
        ax.plot(r["roc_rule"], y, "o", color=cp.MUTED, ms=5, label="rule" if i == 0 else None)
        ax.plot(r["roc_logreg"], y, "o", color=cp.ACCENT, ms=6, label="model" if i == 0 else None)
    ax.axvline(0.5, color=cp.INK, lw=1, ls=":")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"client #{r['size_rank']} · {r['n']:,} pages" for r in rows][::-1], fontsize=7.5)
    cp._style(ax, f"Inside each client: model beats rule in {pc['roc_auc_model_wins']} of "
                  f"{pc['clients_eligible']}",
              "within-client ROC-AUC (0.5 = coin flip)", "")
    ax.grid(axis="x", color=cp.GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    cp.save(fig, "evidence_per_client.svg")


# --------------------------------------------------------------------------------------

def main() -> dict:
    import matplotlib
    matplotlib.use("Agg")
    t0 = time.time()

    frame = cp.build_frame(cp.load_raw())
    d, _ = cp.apply_population_filter(frame)
    y = d["label_declined"].to_numpy()
    groups = d["client_id"].to_numpy()
    X = cp.design_matrix(d)

    scores = {
        "logreg": cp.oof_scores(X, y, groups, "logreg"),
        "rf": cp.oof_scores(X, y, groups, "rf"),
        "hgb": oof_hgb(X, y, groups),
        "rule": cp.baseline_legal_rule(d),
        "random": np.random.RandomState(RANDOM_SEED).rand(len(y)),  # same draw as the pipeline
    }
    point_lr = metric_row(scores["logreg"], y)
    print(f"[{time.time() - t0:5.1f}s] scored: " + ", ".join(
        f"{n} PR-AUC {average_precision_score(y, s):.4f}" for n, s in scores.items()))

    boot = clustered_bootstrap(scores, y, groups)
    print(f"[{time.time() - t0:5.1f}s] bootstrap done")
    perm = permutation_test(X, y, groups, point_lr["pr_auc"])
    print(f"[{time.time() - t0:5.1f}s] permutation test done")
    cal = calibration(scores["logreg"], y)
    cal["confidence_labels"] = confidence_check(scores["logreg"], y,
                                                d["impressions_prev_30d"].to_numpy())
    pc = per_client(d, scores, y)
    sens = sensitivity(frame)
    big = largest_client(d, scores, y)
    print(f"[{time.time() - t0:5.1f}s] calibration, per-client, sensitivity done")

    hgb = boot["intervals"]["hgb"]
    audit = {
        "run": {
            "random_seed": RANDOM_SEED,
            "rows": int(len(y)), "clients": int(len(np.unique(groups))),
            "base_rate": round(float(y.mean()), 4),
            "scores": "every model out-of-fold under GroupKFold(5) by client_id — the same "
                      "folds as capstone_pipeline.py; rule and random need no fitting",
            "gradient_boosting": "HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, "
                                 "max_leaf_nodes=15, min_samples_leaf=100, l2_regularization=1.0)",
        },
        "bootstrap": boot,
        "permutation_test": {k: v for k, v in perm.items() if not k.startswith("_")},
        "complexity_check": {
            "question": "does a gradient-boosted model earn its complexity over logistic regression?",
            "gradient_boosting": {m: hgb[m]["point"] for m in hgb},
            "logistic_regression": {m: boot["intervals"]["logreg"][m]["point"] for m in hgb},
            "verdict": ("no — the paired gap favours logistic regression"
                        if boot["paired_gaps"]["logreg_minus_hgb"]["pr_auc"]["point"] > 0
                        else "yes — gradient boosting ranks better"),
        },
        "calibration": cal,
        "per_client": pc,
        "sensitivity": sens,
        "largest_client": big,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence_audit.json").write_text(json.dumps(audit, indent=2))
    chart_gaps(boot)
    chart_capacity(boot, float(y.mean()))
    chart_permutation(perm)
    chart_calibration(cal)
    chart_per_client(pc)

    g = boot["paired_gaps"]["logreg_minus_rule"]
    print(json.dumps({
        "p@50 model": boot["intervals"]["logreg"]["p@50"],
        "gap vs rule": {m: g[m] for m in ("p@50", "pr_auc", "roc_auc")},
        "gap vs hgb (pr_auc)": boot["paired_gaps"]["logreg_minus_hgb"]["pr_auc"],
        "permutation": audit["permutation_test"],
        "calibration": {k: cal[k] for k in ("brier_skill_score", "expected_calibration_error",
                                            "calibration_slope")},
        "per_client": {k: pc[k] for k in ("clients_eligible", "roc_auc_model_wins",
                                          "roc_auc_sign_test_p", "median_roc_auc_model",
                                          "median_roc_auc_rule")},
        "sensitivity": sens["model_beats_rule_on_pr_auc_in"],
        "largest_client_share": big["largest_client_share_of_pages"],
    }, indent=2))
    print(f"[{time.time() - t0:5.1f}s] wrote work/outputs/evidence_audit.json + 5 figures")
    return audit


if __name__ == "__main__":
    main()
