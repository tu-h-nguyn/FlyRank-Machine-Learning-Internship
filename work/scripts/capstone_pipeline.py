"""
Capstone pipeline — Lane 2: Refresh / Content Opportunity Scoring.

Question
--------
Standing at the START of the most recent 30-day window and using only what was
knowable at that moment, which pages are most likely to lose >=20% of their search
impressions over the NEXT 30 days -- and which of those are worth an editor's time?

Why this file exists
--------------------
Every number in `work/capstone_report.md` and in the deployed paper is produced here.
Run it from the repo root:

    python work/scripts/capstone_pipeline.py

Outputs (all committed, they are the receipts):
    work/outputs/capstone_metrics.json     headline metrics, base rates, split design
    work/outputs/capstone_importance.json  permutation importance, out-of-fold
    work/outputs/capstone_queue_top20.json public-safe top-20 of the action queue
    work/outputs/capstone_queue_summary.json  reason-code / action mix
    work/figures/*.svg                     the paper's charts
    work/outputs/refresh_action_queue.csv  full ranked queue (gitignored by design)

Data
----
The public anonymized starter slice that ships with this repo
(`data/raw/content_refresh_anonymized.csv`, 30,000 pages x 44 columns, 32
pseudonymized clients, one trailing-90-day snapshot). If HF_TOKEN is present the
same feature contract can be rebuilt on the gated warehouse release; see
`notebooks/03_working_with_the_full_release.ipynb`. This run does not use it.

Seeds are fixed (RANDOM_SEED = 42). Re-running reproduces every number.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

RANDOM_SEED = 42
N_SPLITS = 5
PRIMARY_MODEL = "logreg"   # it beat the random forest on the honest split; simplicity wins ties
PRIMARY_NAME = "Model (logistic regression, honest features)"
MIN_PREV_IMPRESSIONS = 100      # demand floor: a page must be worth an editor's hour
DECLINE_THRESHOLD_PCT = -20.0   # matches the product definition of trend_direction == "down"
K_VALUES = [10, 20, 50, 100, 200, 500]

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "raw" / "content_refresh_anonymized.csv"
OUT = REPO / "work" / "outputs"
FIG = REPO / "work" / "figures"

# --------------------------------------------------------------------------------------
# Field contract. Written down once, here, so the paper and the notebooks cannot drift.
# --------------------------------------------------------------------------------------

# Knowable at the decision point (end of the prev-30d window). Everything else is banned.
HONEST_NUMERIC = [
    "log_impr_prev30",
    "log_impr_first30",
    "prior_impr_trend_pct",
    "log_clicks_prev30",
    "prior_ctr",
    "prior_ctr_delta",
    "prior_click_trend_pct",
    "log_sessions_prev30",
    "prior_session_trend_pct",
    "sessions_per_1k_impr_prev30",
    "impr_share_prev30",
    "content_age_days_at_decision",
    "word_count",
    "has_word_count",
    "search_volume",
    "competition",
    "cpc",
    "has_keyword_data",
]
HONEST_CATEGORICAL = ["content_type", "main_intent"]

# Deliberately excluded, with the reason. This dict is rendered straight into the paper.
EXCLUDED = {
    "trend_pct": "label source (the label is derived from it) — circular",
    "trend_direction": "label source — circular",
    "impressions_last_30d": "inside the outcome window",
    "clicks_last_30d": "inside the outcome window",
    "sessions_last_30d": "inside the outcome window",
    "impressions_90d": "90-day total spans the outcome window",
    "clicks_90d": "90-day total spans the outcome window",
    "pageviews_90d": "90-day total spans the outcome window",
    "sessions_90d": "90-day total spans the outcome window",
    "users_90d": "90-day total spans the outcome window",
    "engaged_sessions_90d": "90-day total spans the outcome window",
    "ai_sessions_90d": "90-day total spans the outcome window (and AI sessions are sparse)",
    "scroll_events_90d": "90-day total spans the outcome window",
    "days_with_impressions": "counted across the outcome window",
    "days_with_sessions": "counted across the outcome window",
    "ctr": "90-day rate spans the outcome window",
    "avg_position": "90-day mean spans the outcome window (no earlier-window position exists)",
    "engagement_rate": "90-day rate spans the outcome window",
    "scroll_rate": "90-day rate spans the outcome window",
    "ai_traffic_pct": "90-day rate spans the outcome window",
    "days_since_last_update": "measured at export: 68% of pages were updated INSIDE the outcome window",
    "freshness_tier": "bucket of days_since_last_update — same contamination",
    "impression_tier": "product bucket built from a window-spanning total",
    "position_tier": "product bucket built from a window-spanning mean",
    "age_tier / age_tier_order / word_count_tier / char_count_tier": "product buckets, kept as context only",
    "provider_used / model_used": "content-production metadata, not an observable search signal",
    "content_id / client_id": "pseudonymous IDs — grouping and splitting only, never features",
}

# The window-overlapping set used ONLY to demonstrate what leakage looks like.
LEAKY_EXTRA = [
    "impressions_90d",
    "clicks_90d",
    "sessions_90d",
    "days_with_impressions",
    "ctr",
    "avg_position",
    "engagement_rate",
    "days_since_last_update",
]


# --------------------------------------------------------------------------------------
# Feature build
# --------------------------------------------------------------------------------------

def load_raw() -> pd.DataFrame:
    if not DATA.exists():  # Colab / fresh clone without the sample
        url = ("https://raw.githubusercontent.com/tu-h-nguyn/"
               "FlyRank-End-to-End-Machine-Learning-Project-Internship"
               "/main/data/raw/content_refresh_anonymized.csv")
        return pd.read_csv(url)
    return pd.read_csv(DATA)


def build_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Split the 90-day window into three 30-day sub-windows and build decision-time features.

    The snapshot's 90-day totals decompose exactly:
        first30 (days 61-90 back) + prev30 (days 31-60 back) + last30 (days 1-30 back)
    The label lives in last30. Only first30 and prev30 may become features.
    """
    d = df.copy()

    for metric in ["impressions", "clicks", "sessions"]:
        d[f"{metric}_first30"] = (
            d[f"{metric}_90d"] - d[f"{metric}_last_30d"] - d[f"{metric}_prev_30d"]
        ).clip(lower=0)

    def pct_change(new: pd.Series, old: pd.Series) -> pd.Series:
        return ((new - old) / old.replace(0, np.nan) * 100).clip(-100, 300).fillna(0.0)

    d["log_impr_prev30"] = np.log1p(d["impressions_prev_30d"])
    d["log_impr_first30"] = np.log1p(d["impressions_first30"])
    d["log_clicks_prev30"] = np.log1p(d["clicks_prev_30d"])
    d["log_sessions_prev30"] = np.log1p(d["sessions_prev_30d"])

    # Prior momentum: the movement the editor could already SEE at the decision point.
    d["prior_impr_trend_pct"] = pct_change(d["impressions_prev_30d"], d["impressions_first30"])
    d["prior_click_trend_pct"] = pct_change(d["clicks_prev_30d"], d["clicks_first30"])
    d["prior_session_trend_pct"] = pct_change(d["sessions_prev_30d"], d["sessions_first30"])

    # Prior click-through, and how it moved between the two visible windows (x100, as in the dict).
    d["prior_ctr"] = (
        d["clicks_prev_30d"] / d["impressions_prev_30d"].replace(0, np.nan) * 100
    ).fillna(0.0)
    ctr_first30 = (
        d["clicks_first30"] / d["impressions_first30"].replace(0, np.nan) * 100
    ).fillna(0.0)
    d["prior_ctr_delta"] = d["prior_ctr"] - ctr_first30

    d["sessions_per_1k_impr_prev30"] = (
        d["sessions_prev_30d"] / d["impressions_prev_30d"].replace(0, np.nan) * 1000
    ).fillna(0.0)

    # How much of the visible 60 days this page's demand sat in the more recent half.
    visible60 = d["impressions_prev_30d"] + d["impressions_first30"]
    d["impr_share_prev30"] = (
        d["impressions_prev_30d"] / visible60.replace(0, np.nan)
    ).fillna(0.0)

    d["content_age_days_at_decision"] = (d["content_age_days"] - 30).clip(lower=0)

    # Missingness is systematic (it follows content_type) — flag it, never blind-fill it.
    d["has_word_count"] = d["word_count"].notna().astype(int)
    d["word_count"] = d["word_count"].fillna(d["word_count"].median())
    d["has_keyword_data"] = d["search_volume"].notna().astype(int)
    for col in ["search_volume", "competition", "cpc"]:
        d[col] = d[col].fillna(0.0)
    d["main_intent"] = d["main_intent"].fillna("unknown")

    # Label: the observed next-30-day outcome, exactly the product's "down" definition.
    d["label_declined"] = (d["trend_pct"] < DECLINE_THRESHOLD_PCT).astype(int)
    return d


def apply_population_filter(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Keep pages whose decline would actually be worth an editor's time."""
    steps = {"rows_start": int(len(d))}
    keep = d["impressions_prev_30d"] >= MIN_PREV_IMPRESSIONS
    steps[f"dropped_prev30_impressions_below_{MIN_PREV_IMPRESSIONS}"] = int((~keep).sum())
    d = d[keep].copy()
    steps["rows_modelled"] = int(len(d))
    steps["clients_modelled"] = int(d["client_id"].nunique())
    return d, steps


def design_matrix(d: pd.DataFrame, extra_numeric: list[str] | None = None) -> pd.DataFrame:
    numeric = list(HONEST_NUMERIC) + list(extra_numeric or [])
    X = d[numeric].copy()
    for col in HONEST_CATEGORICAL:
        dummies = pd.get_dummies(d[col].fillna("unknown"), prefix=col, drop_first=True)
        X = pd.concat([X, dummies], axis=1)
    return X.astype(float).replace([np.inf, -np.inf], 0.0).fillna(0.0)


# --------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------

def precision_at_k(scores: np.ndarray, labels: np.ndarray, k: int) -> float:
    k = min(k, len(scores))
    order = np.argsort(-np.asarray(scores), kind="stable")
    return float(np.asarray(labels)[order[:k]].mean())


def recall_at_k(scores: np.ndarray, labels: np.ndarray, k: int) -> float:
    k = min(k, len(scores))
    order = np.argsort(-np.asarray(scores), kind="stable")
    labels = np.asarray(labels)
    positives = labels.sum()
    return float(labels[order[:k]].sum() / positives) if positives else float("nan")


def score_report(name: str, scores: np.ndarray, labels: np.ndarray) -> dict:
    base = float(np.mean(labels))
    rep = {
        "name": name,
        "base_rate": round(base, 4),
        "roc_auc": round(float(roc_auc_score(labels, scores)), 4),
        "pr_auc": round(float(average_precision_score(labels, scores)), 4),
        "pr_auc_lift_vs_base": round(float(average_precision_score(labels, scores)) / base, 3),
        "precision_at_k": {},
        "recall_at_k": {},
        "lift_at_k": {},
    }
    for k in K_VALUES:
        p = precision_at_k(scores, labels, k)
        rep["precision_at_k"][str(k)] = round(p, 4)
        rep["recall_at_k"][str(k)] = round(recall_at_k(scores, labels, k), 4)
        rep["lift_at_k"][str(k)] = round(p / base, 3)
    return rep


# --------------------------------------------------------------------------------------
# Out-of-fold scoring: every metric below is out-of-fold, grouped by client.
# --------------------------------------------------------------------------------------

def stability_check(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, kind: str,
                    seeds=(42, 7, 2024, 101, 777)) -> dict:
    """Re-draw the client holdout five times. A headline number that moves a lot is a warning."""
    pr, p50 = [], []
    for seed in seeds:
        tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.25,
                                        random_state=seed).split(X, y, groups))
        model = make_model(kind)
        model.fit(X.iloc[tr], y[tr])
        s = model.predict_proba(X.iloc[te])[:, 1]
        pr.append(float(average_precision_score(y[te], s)))
        p50.append(precision_at_k(s, y[te], 50))
    return {
        "seeds": list(seeds),
        "pr_auc_mean": round(float(np.mean(pr)), 4),
        "pr_auc_std": round(float(np.std(pr)), 4),
        "pr_auc_min": round(float(np.min(pr)), 4),
        "pr_auc_max": round(float(np.max(pr)), 4),
        "precision_at_50_mean": round(float(np.mean(p50)), 4),
        "precision_at_50_std": round(float(np.std(p50)), 4),
    }


def make_model(kind: str):
    if kind == "logreg":
        return Pipeline([
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, random_state=RANDOM_SEED)),
        ])
    if kind == "rf":
        return RandomForestClassifier(
            n_estimators=300, max_depth=8, min_samples_leaf=50,
            random_state=RANDOM_SEED, n_jobs=-1,
        )
    raise ValueError(kind)


def oof_scores(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, kind: str) -> np.ndarray:
    oof = np.zeros(len(y), dtype=float)
    for train_idx, test_idx in GroupKFold(n_splits=N_SPLITS).split(X, y, groups):
        model = make_model(kind)
        model.fit(X.iloc[train_idx], y[train_idx])
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
    return oof


def random_split_scores(X: pd.DataFrame, y: np.ndarray, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """The dishonest-but-informative comparison: ignore clients, split rows at random."""
    rng = np.random.RandomState(RANDOM_SEED)
    idx = rng.permutation(len(y))
    cut = int(len(y) * 0.8)
    tr, te = idx[:cut], idx[cut:]
    model = make_model(kind)
    model.fit(X.iloc[tr], y[tr])
    return model.predict_proba(X.iloc[te])[:, 1], y[te]


# --------------------------------------------------------------------------------------
# Baselines (transparent, no fitted weights)
# --------------------------------------------------------------------------------------

def baseline_w4_rule(d: pd.DataFrame) -> np.ndarray:
    """The Week-4 rule exactly as it was frozen: stale x visible x impressions.

    It reads two columns we later proved are contaminated by the outcome window
    (days_since_last_update, impressions_90d). Kept unchanged, on purpose, as the
    thing to beat and as the illustration of why it cannot be shipped.
    """
    stale = (d["days_since_last_update"] >= 180).astype(int)
    visible = (d["impressions_90d"] >= 1000).astype(int)
    valid_rank = (d["avg_position"] > 0).astype(int)
    return (stale * visible * valid_rank * d["impressions_90d"]).to_numpy(dtype=float)


def baseline_legal_rule(d: pd.DataFrame) -> np.ndarray:
    """The same idea, rebuilt from decision-time columns only.

    Plain words: a page is worth reviewing first if it already lost ground between the
    two windows an editor can see, and it still carries enough demand to matter.
    """
    slipping = (d["prior_impr_trend_pct"] < 0).astype(int)
    demand = np.log1p(d["impressions_prev_30d"])
    weak_ctr = (d["prior_ctr"] < d["prior_ctr"].median()).astype(int)
    return (slipping * demand * (1 + 0.5 * weak_ctr)).to_numpy(dtype=float)


# The four states the lane asks about. Two layers, kept strictly apart:
#
#   decision_state  — what an editor can see AT the decision point (prior window only).
#                     Safe to act on. Only three values are observable here, because the
#                     slice offers exactly TWO visible 30-day windows, i.e. one delta.
#   outcome_state   — what actually happened in the outcome window. Reporting and
#                     evaluation ONLY. It is label-side information and must never be a
#                     feature, nor be read as something the engine predicts.
#
# "recovering" needs two consecutive deltas (a fall, then a rise). With one visible delta
# it cannot be detected before the fact — so this engine can REPORT recovery but cannot
# PREDICT it. Restoring that would need the warehouse's daily table.

DECISION_STATES = ["slipping", "steady", "spiking"]
OUTCOME_STATES = ["declining", "recovering", "growing", "stable"]


def decision_state(d: pd.DataFrame) -> pd.Series:
    """Knowable at the decision point: the one delta between first30 and prev30."""
    prior = d["prior_impr_trend_pct"]
    return pd.Series(
        np.where(prior < -20, "slipping", np.where(prior > 20, "spiking", "steady")),
        index=d.index, name="decision_state")


def outcome_state(d: pd.DataFrame) -> pd.Series:
    """Observed after the fact. Evaluation only — never an input, never a prediction."""
    prior, out = d["prior_impr_trend_pct"], d["trend_pct"]
    return pd.Series(
        np.select(
            [out < DECLINE_THRESHOLD_PCT,
             (out > 20) & (prior < -20),
             (out > 20) & (prior >= -20)],
            ["declining", "recovering", "growing"],
            default="stable"),
        index=d.index, name="outcome_state")


def reason_codes(row: pd.Series, ctr_median: float) -> tuple[str, str]:
    """Why this page is in the queue, and what an editor should do with it."""
    codes = []
    if row["prior_impr_trend_pct"] <= -20:
        codes.append("visibility_slipping")
    if row["prior_click_trend_pct"] <= -20 and row["prior_impr_trend_pct"] > -20:
        codes.append("clicks_falling_while_visible")
    if row["prior_ctr"] < ctr_median and row["impressions_prev_30d"] >= 500:
        codes.append("low_ctr_high_exposure")
    if row["impressions_prev_30d"] >= 3000:
        codes.append("high_demand_page")
    if row["content_age_days_at_decision"] >= 365:
        codes.append("aging_content")
    if row["has_keyword_data"] == 1 and row["search_volume"] >= 1000:
        codes.append("valuable_keyword")
    # Growing pages are part of this lane too — the queue should say so rather than
    # staying silent about them.
    if row["prior_impr_trend_pct"] > 20 and row["impressions_prev_30d"] >= 500:
        codes.append("growing_with_demand")
    # Evidence-backed, not a hunch: the >+50% momentum bucket declines at 58.7%, above
    # the 52.4% trough of the +20..+50% bucket (w04_signal_audit). A jump is not by
    # itself good news.
    if row["prior_impr_trend_pct"] > 50:
        codes.append("spiking_may_revert")
    if not codes:
        codes.append("model_pattern_only")

    gaining = {"growing_with_demand", "spiking_may_revert"} & set(codes)
    losing = {"visibility_slipping", "clicks_falling_while_visible",
              "low_ctr_high_exposure"} & set(codes)
    if gaining and not losing:
        return "|".join(codes), "protect_and_watch"

    if "visibility_slipping" in codes and "high_demand_page" in codes:
        action = "protect_and_refresh"
    elif "visibility_slipping" in codes:
        action = "review_for_refresh"
    elif "clicks_falling_while_visible" in codes or "low_ctr_high_exposure" in codes:
        action = "review_metadata_and_intent"
    elif "aging_content" in codes:
        action = "review_for_update"
    else:
        action = "monitor"
    return "|".join(codes), action


def confidence_label(prob: float, impressions_prev30: float) -> str:
    if prob >= 0.75 and impressions_prev30 >= 1000:
        return "high"
    if prob >= 0.60:
        return "medium"
    return "low"


# --------------------------------------------------------------------------------------
# Charts — one message per chart, light theme, SVG so the paper stays self-contained.
# --------------------------------------------------------------------------------------

INK = "#1f2933"
MUTED = "#7b8794"
ACCENT = "#0b6bcb"
WARN = "#c2410c"
GOOD = "#0f766e"
GRID = "#dfe3e8"


def _style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, color=INK, fontsize=12, pad=12, loc="left", fontweight="bold")
    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.tick_params(colors=MUTED, labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, format="svg", bbox_inches="tight", transparent=False,
                facecolor="white")
    import matplotlib.pyplot as plt
    plt.close(fig)


def chart_precision_at_k(reports: dict, base_rate: float) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    styles = {
        "Model (logistic regression, honest features)": (ACCENT, "-", "o"),
        "Rule baseline (decision-time columns)": (GOOD, "-", "s"),
        "Week-4 rule (window-contaminated)": (WARN, "--", "^"),
    }
    for label, (color, ls, marker) in styles.items():
        rep = reports[label]
        ks = [int(k) for k in rep["precision_at_k"]]
        vs = [rep["precision_at_k"][str(k)] for k in ks]
        ax.plot(ks, vs, color=color, linestyle=ls, marker=marker, markersize=4,
                linewidth=1.8, label=label)
    ax.axhline(base_rate, color=MUTED, linestyle=":", linewidth=1.4,
               label=f"Base rate ({base_rate:.1%} of pages declined)")
    ax.set_xscale("log")
    ax.set_xticks(K_VALUES)
    ax.set_xticklabels([str(k) for k in K_VALUES])
    ax.set_ylim(0, 1)
    _style(ax, "Precision@K — of the top K pages the queue hands an editor, how many really declined",
           "K (pages an editor actually reviews, log scale)", "Precision@K")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="lower left")
    save(fig, "precision_at_k.svg")


def chart_honest_vs_leaky(rows: list[tuple[str, float, float]], base_rate: float) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    names = [r[0] for r in rows]
    pr = [r[1] for r in rows]
    p50 = [r[2] for r in rows]
    y = np.arange(len(names))
    ax.barh(y - 0.19, pr, height=0.36, color=ACCENT, label="PR-AUC (average precision)")
    ax.barh(y + 0.19, p50, height=0.36, color="#9dc7f0", label="Precision@50")
    ax.axvline(base_rate, color=MUTED, linestyle=":", linewidth=1.4,
               label=f"Base rate {base_rate:.1%}")
    for i, (a, b) in enumerate(zip(pr, p50)):
        ax.text(a + 0.012, i - 0.19, f"{a:.3f}", va="center", fontsize=8, color=INK)
        ax.text(b + 0.012, i + 0.19, f"{b:.3f}", va="center", fontsize=8, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.08)
    _style(ax, "What leakage buys you: a beautiful score that is not a real skill",
           "Score (out-of-fold, grouped by client)", "")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper center",
              bbox_to_anchor=(0.5, -0.16), ncol=3)
    save(fig, "honest_vs_leaky.svg")


def chart_importance(importance: list[dict]) -> None:
    import matplotlib.pyplot as plt
    top = importance[:10][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.barh([t["feature"] for t in top], [t["importance_mean"] for t in top],
            xerr=[t["importance_std"] for t in top], color=ACCENT, height=0.62,
            error_kw={"ecolor": MUTED, "elinewidth": 1})
    ax.tick_params(axis="y", labelsize=8.5)
    _style(ax, "What the model leans on (permutation importance, out-of-fold)",
           "Drop in PR-AUC when the column is shuffled", "")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    save(fig, "feature_importance.svg")


def chart_risk_deciles(deciles: list[dict], base_rate: float) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    xs = [d["decile"] for d in deciles]
    ys = [d["observed_decline_rate"] for d in deciles]
    colors = [WARN if v >= base_rate else "#9dc7f0" for v in ys]
    ax.bar(xs, ys, color=colors, width=0.72)
    ax.axhline(base_rate, color=MUTED, linestyle=":", linewidth=1.4)
    ax.text(0.6, base_rate + 0.02, f"base rate {base_rate:.1%}", color=MUTED, fontsize=8)
    ax.set_xticks(xs)
    ax.set_ylim(0, 1)
    _style(ax, "Observed decline rate by predicted-risk decile (out-of-fold)",
           "Predicted-risk decile (10 = riskiest)", "Share of pages that declined")
    save(fig, "risk_deciles.svg")


def chart_queue_mix(mix: dict) -> None:
    import matplotlib.pyplot as plt
    items = sorted(mix.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1],
            color=GOOD, height=0.62)
    for i, (_, v) in enumerate(items[::-1]):
        ax.text(v + 1, i, str(v), va="center", fontsize=8, color=INK)
    ax.tick_params(axis="y", labelsize=8.5)
    _style(ax, "Reason codes behind the top 200 of the action queue",
           "Pages carrying this reason code", "")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    save(fig, "queue_reason_mix.svg")


# Four-state composition. Palette validated with the dataviz skill's checker
# (chroma floor, CVD separation, normal-vision floor, contrast vs the white plate):
#   #c2410c / #0b6bcb / #0f8a76 pass all checks; #7b8794 is the deliberate neutral
#   midpoint for "stable", not a fourth hue. Tritan separation between the blue and
#   the teal is modest, so every segment is direct-labelled and separated by a 2px
#   surface gap — identity is never carried by colour alone.
STATE_COLORS = {
    "declining": "#c2410c",
    "recovering": "#0b6bcb",
    "growing": "#0f8a76",
    "stable": "#7b8794",
}


def chart_state_mix(decile_mix: list[dict]) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    deciles = [d["decile"] for d in decile_mix]
    bottom = np.zeros(len(deciles))
    for state in ["declining", "stable", "recovering", "growing"]:
        vals = np.array([d[state] for d in decile_mix])
        ax.bar(deciles, vals, bottom=bottom, width=0.74, color=STATE_COLORS[state],
               label=state, linewidth=1.6, edgecolor="white")   # 2px surface gap
        for x, v, b in zip(deciles, vals, bottom):
            if v >= 0.07:                      # direct label = the secondary encoding
                ax.text(x, b + v / 2, f"{v * 100:.0f}", ha="center", va="center",
                        fontsize=7.5, color="white", fontweight="bold")
        bottom += vals
    ax.set_xticks(deciles)
    ax.set_ylim(0, 1)
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    _style(ax, "What actually happened to the pages in each risk decile",
           "Predicted-risk decile (10 = riskiest)", "Share of pages")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper center",
              bbox_to_anchor=(0.5, -0.14), ncol=4)
    save(fig, "queue_state_mix.svg")


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def main() -> dict:
    import matplotlib
    matplotlib.use("Agg")

    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    raw = load_raw()
    frame = build_frame(raw)
    d, population = apply_population_filter(frame)

    y = d["label_declined"].to_numpy()
    groups = d["client_id"].to_numpy()
    base_rate = float(y.mean())
    print(f"rows={len(d):,}  clients={d['client_id'].nunique()}  base_rate={base_rate:.4f}")

    X_honest = design_matrix(d)
    X_leaky = design_matrix(d, extra_numeric=LEAKY_EXTRA)

    reports: dict[str, dict] = {}

    # --- baselines (no fitting, so the whole population is the evaluation set) ---
    reports["Week-4 rule (window-contaminated)"] = score_report(
        "Week-4 rule (window-contaminated)", baseline_w4_rule(d), y)
    reports["Rule baseline (decision-time columns)"] = score_report(
        "Rule baseline (decision-time columns)", baseline_legal_rule(d), y)
    rng = np.random.RandomState(RANDOM_SEED)
    reports["Random ordering"] = score_report("Random ordering", rng.rand(len(y)), y)

    # --- honest models, out-of-fold, grouped by client ---
    oof_lr = oof_scores(X_honest, y, groups, "logreg")
    oof_rf = oof_scores(X_honest, y, groups, "rf")
    reports["Model (logistic regression, honest features)"] = score_report(
        "Model (logistic regression, honest features)", oof_lr, y)
    reports["Model (random forest, honest features)"] = score_report(
        "Model (random forest, honest features)", oof_rf, y)
    oof_primary = oof_lr if PRIMARY_MODEL == "logreg" else oof_rf

    # --- the leakage demonstration: same model, window-overlapping columns added ---
    oof_leaky = oof_scores(X_leaky, y, groups, "rf")
    reports["Model (random forest, window-overlapping features)"] = score_report(
        "Model (random forest, window-overlapping features)", oof_leaky, y)

    # --- the split-design gap: grouped (honest) vs random (memorises the client) ---
    rand_scores, rand_y = random_split_scores(X_honest, y, PRIMARY_MODEL)
    split_gap = {
        "grouped_by_client_pr_auc": reports[PRIMARY_NAME]["pr_auc"],
        "random_row_split_pr_auc": round(float(average_precision_score(rand_y, rand_scores)), 4),
        "random_row_split_base_rate": round(float(rand_y.mean()), 4),
    }
    split_gap["gap"] = round(
        split_gap["random_row_split_pr_auc"] - split_gap["grouped_by_client_pr_auc"], 4)

    # --- permutation importance, out-of-fold, on the honest model ---
    from sklearn.inspection import permutation_importance
    tr_idx, te_idx = next(GroupShuffleSplit(
        n_splits=1, test_size=0.25, random_state=RANDOM_SEED).split(X_honest, y, groups))
    imp_model = make_model(PRIMARY_MODEL)
    imp_model.fit(X_honest.iloc[tr_idx], y[tr_idx])
    perm = permutation_importance(
        imp_model, X_honest.iloc[te_idx], y[te_idx], n_repeats=10,
        random_state=RANDOM_SEED, scoring="average_precision", n_jobs=-1)
    importance = sorted(
        [{"feature": f,
          "importance_mean": round(float(m), 5),
          "importance_std": round(float(s), 5)}
         for f, m, s in zip(X_honest.columns, perm.importances_mean, perm.importances_std)],
        key=lambda r: -r["importance_mean"])

    # --- risk deciles (out-of-fold) ---
    dec = pd.DataFrame({"score": oof_primary, "y": y})
    dec["decile"] = pd.qcut(dec["score"].rank(method="first"), 10, labels=range(1, 11)).astype(int)
    deciles = [
        {"decile": int(k),
         "observed_decline_rate": round(float(g["y"].mean()), 4),
         "n": int(len(g)),
         "lift": round(float(g["y"].mean()) / base_rate, 3)}
        for k, g in dec.groupby("decile")
    ]

    # --- the action queue: score, reason codes, action, confidence ---
    q = d.copy()
    q["risk_score"] = oof_primary
    ctr_median = float(q["prior_ctr"].median())
    codes_actions = q.apply(lambda r: reason_codes(r, ctr_median), axis=1)
    q["reason_codes"] = [c for c, _ in codes_actions]
    q["action"] = [a for _, a in codes_actions]
    q["confidence"] = [confidence_label(p, i)
                       for p, i in zip(q["risk_score"], q["impressions_prev_30d"])]
    q["decision_state"] = decision_state(q)      # actionable
    q["outcome_state"] = outcome_state(q)        # evaluation only — clearly separated
    q = q.sort_values("risk_score", ascending=False)
    queue_cols = ["content_id", "risk_score", "action", "reason_codes", "confidence",
                  "decision_state", "impressions_prev_30d", "prior_impr_trend_pct",
                  "prior_ctr", "content_age_days_at_decision",
                  "outcome_state", "label_declined"]
    q[queue_cols].to_csv(OUT / "refresh_action_queue.csv", index=False)

    top200 = q.head(200)
    mix: dict[str, int] = {}
    for codes in top200["reason_codes"]:
        for c in codes.split("|"):
            mix[c] = mix.get(c, 0) + 1
    queue_summary = {
        "queue_rows": int(len(q)),
        "top200_reason_code_mix": mix,
        "top200_action_mix": {k: int(v) for k, v in top200["action"].value_counts().items()},
        "top200_confidence_mix": {k: int(v) for k, v in top200["confidence"].value_counts().items()},
        "top200_precision": round(float(top200["label_declined"].mean()), 4),
        "top200_share_of_all_prev30_impressions": round(
            float(top200["impressions_prev_30d"].sum() / q["impressions_prev_30d"].sum()), 4),
        "action_mix_full_queue": {k: int(v) for k, v in q["action"].value_counts().items()},
        "top200_decision_state_mix": {k: int(v) for k, v in
                                      top200["decision_state"].value_counts().items()},
    }
    # What actually happened to the pages the engine ranks highest — the honest way to
    # ask "does this queue surface decline, or does it just surface big pages?"
    states = {
        "definitions": {
            "decision_state": {
                "when": "knowable at the decision point (prior window only) — safe to act on",
                "slipping": "prior-window impressions fell more than 20%",
                "spiking": "prior-window impressions rose more than 20%",
                "steady": "within +/-20%",
            },
            "outcome_state": {
                "when": "observed in the outcome window — REPORTING AND EVALUATION ONLY, "
                        "never a feature and never predicted by the engine",
                "declining": f"outcome impressions fell more than {abs(DECLINE_THRESHOLD_PCT):.0f}%",
                "recovering": "outcome rose more than 20% AFTER a prior-window fall of more than 20%",
                "growing": "outcome rose more than 20% without a prior-window fall",
                "stable": "everything else",
            },
            "why_recovery_cannot_be_predicted_here":
                "detecting a recovery before the fact needs two consecutive deltas (a fall "
                "then a rise); this slice exposes only two pre-decision windows, i.e. one "
                "delta. The engine reports recovery, it does not predict it.",
        },
        "population_mix": {},
        "top_k_outcome_mix": {},
        "decile_outcome_mix": [],
        "decision_state_mix": {},
    }
    q_out, q_dec = q["outcome_state"], q["decision_state"]
    states["population_mix"] = {k: int(v) for k, v in q_out.value_counts().items()}
    states["decision_state_mix"] = {k: int(v) for k, v in q_dec.value_counts().items()}
    for k in [50, 200, 500, 1000]:
        head = q.head(k)["outcome_state"].value_counts()
        states["top_k_outcome_mix"][str(k)] = {
            st: {"n": int(head.get(st, 0)), "share": round(float(head.get(st, 0)) / k, 4)}
            for st in OUTCOME_STATES
        }
    q_dec_bins = pd.qcut(q["risk_score"].rank(method="first"), 10, labels=range(1, 11))
    for dec, grp in q.groupby(q_dec_bins, observed=True):
        vc = grp["outcome_state"].value_counts()
        states["decile_outcome_mix"].append({
            "decile": int(dec), "n": int(len(grp)),
            **{st: round(float(vc.get(st, 0)) / len(grp), 4) for st in OUTCOME_STATES},
        })

    top20 = [
        {"rank": i + 1,
         "content_id": r.content_id,               # pseudonymous, safe to publish
         "risk_score": round(float(r.risk_score), 4),
         "action": r.action,
         "reason_codes": r.reason_codes,
         "confidence": r.confidence,
         "decision_state": r.decision_state,
         "outcome_state": r.outcome_state,
         "impressions_prev_30d": int(r.impressions_prev_30d),
         "prior_impr_trend_pct": round(float(r.prior_impr_trend_pct), 1),
         "prior_ctr_pct": round(float(r.prior_ctr), 2),
         "declined_next_30d": int(r.label_declined)}
        for i, r in enumerate(q.head(20).itertuples())
    ]

    stability = stability_check(X_honest, y, groups, PRIMARY_MODEL)

    # Direction of each signal, read off the standardised coefficients (interpretation only).
    coef_model = make_model("logreg")
    coef_model.fit(X_honest, y)
    coefs = sorted(
        [{"feature": f, "std_coefficient": round(float(c), 4),
          "direction": "raises predicted decline risk" if c > 0 else "lowers predicted decline risk"}
         for f, c in zip(X_honest.columns, coef_model.named_steps["clf"].coef_[0])],
        key=lambda r: -abs(r["std_coefficient"]))
    (OUT / "capstone_coefficients.json").write_text(json.dumps(coefs, indent=2))

    metrics = {
        "run": {
            "random_seed": RANDOM_SEED,
            "cv": f"GroupKFold(n_splits={N_SPLITS}) grouped by client_id, all metrics out-of-fold",
            "dataset": "data/raw/content_refresh_anonymized.csv (public anonymized starter slice)",
            "rows_raw": int(len(raw)),
            "label": f"impressions in the last 30 days fell more than {abs(DECLINE_THRESHOLD_PCT):.0f}% "
                     f"versus the previous 30 days (trend_direction == 'down')",
            "decision_point": "the start of the last 30-day window",
            "population_filter": f"impressions_prev_30d >= {MIN_PREV_IMPRESSIONS}",
        },
        "population": population,
        "base_rate": round(base_rate, 4),
        "positives": int(y.sum()),
        "features_used": list(X_honest.columns),
        "features_excluded": EXCLUDED,
        "reports": reports,
        "split_design_gap": split_gap,
        "stability_across_client_holdouts": stability,
        "risk_deciles": deciles,
    }

    (OUT / "capstone_metrics.json").write_text(json.dumps(metrics, indent=2))
    (OUT / "capstone_importance.json").write_text(json.dumps(importance, indent=2))
    (OUT / "capstone_queue_top20.json").write_text(json.dumps(top20, indent=2))
    (OUT / "capstone_queue_summary.json").write_text(json.dumps(queue_summary, indent=2))
    (OUT / "capstone_states.json").write_text(json.dumps(states, indent=2))

    chart_precision_at_k(reports, base_rate)
    chart_honest_vs_leaky([
        ("Random forest, window-overlapping features\n(what leakage looks like)",
         reports["Model (random forest, window-overlapping features)"]["pr_auc"],
         reports["Model (random forest, window-overlapping features)"]["precision_at_k"]["50"]),
        ("Logistic regression, honest features\n(the shipped model)",
         reports["Model (logistic regression, honest features)"]["pr_auc"],
         reports["Model (logistic regression, honest features)"]["precision_at_k"]["50"]),
        ("Random forest, honest features",
         reports["Model (random forest, honest features)"]["pr_auc"],
         reports["Model (random forest, honest features)"]["precision_at_k"]["50"]),
        ("Rule baseline, decision-time columns",
         reports["Rule baseline (decision-time columns)"]["pr_auc"],
         reports["Rule baseline (decision-time columns)"]["precision_at_k"]["50"]),
        ("Week-4 rule (window-contaminated)",
         reports["Week-4 rule (window-contaminated)"]["pr_auc"],
         reports["Week-4 rule (window-contaminated)"]["precision_at_k"]["50"]),
    ], base_rate)
    chart_importance(importance)
    chart_risk_deciles(deciles, base_rate)
    chart_queue_mix(mix)
    chart_state_mix(states["decile_outcome_mix"])

    print(json.dumps({k: {"pr_auc": v["pr_auc"], "p@50": v["precision_at_k"]["50"],
                          "p@200": v["precision_at_k"]["200"], "roc": v["roc_auc"]}
                      for k, v in reports.items()}, indent=2))
    print("split gap:", split_gap)
    print("stability:", stability)
    print("top coefficients:", [(c["feature"], c["std_coefficient"]) for c in coefs[:8]])
    print("top-20 importance:", [i["feature"] for i in importance[:8]])
    print("queue:", json.dumps(queue_summary, indent=2)[:800])
    print("states — top-50 outcome mix:",
          {k: v["share"] for k, v in states["top_k_outcome_mix"]["50"].items()})
    print("states — population mix:", states["population_mix"])
    return metrics


if __name__ == "__main__":
    main()
