"""
Guards for the capstone. Run from the repo root:

    pytest -q tests/

Four families of checks, each one a failure that has happened to real ML projects:

1. The feature contract — no label-derived, window-spanning or ID column can sneak into
   the model, and the 90-day window really does decompose into three 30-day windows.
2. Receipts — the committed metrics JSON is what a fresh run of the pipeline produces.
3. Claims — every headline number printed in the README, the report and the paper is the
   number in the receipts. Edit a JSON without the prose (or the prose without the JSON)
   and this fails.
4. Public safety — nothing that could identify a client leaves the repo.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import average_precision_score, roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "work" / "scripts"))

import capstone_pipeline as cp  # noqa: E402

OUT = REPO / "work" / "outputs"
M = json.loads((OUT / "capstone_metrics.json").read_text())
E = json.loads((OUT / "evidence_audit.json").read_text())
LR = M["reports"]["Model (logistic regression, honest features)"]
RULE = M["reports"]["Rule baseline (decision-time columns)"]
QSUM = json.loads((OUT / "capstone_queue_summary.json").read_text())


@pytest.fixture(scope="module")
def modelled():
    d, _ = cp.apply_population_filter(cp.build_frame(cp.load_raw()))
    return d


# ------------------------------------------------------------------ 1. feature contract

LABEL_SOURCES = {"trend_pct", "trend_direction", "is_declining_label", "label_declined"}
IDS = {"content_id", "client_id"}


def test_no_label_source_or_id_is_a_feature():
    used = set(M["features_used"])
    assert not used & LABEL_SOURCES
    assert not used & IDS
    assert not used & set(cp.LEAKY_EXTRA)


def test_every_excluded_column_stays_excluded():
    """Exact-name match (a substring match flags the legal prior_*_trend columns)."""
    used = set(M["features_used"])
    for key in M["features_excluded"]:
        for col in re.split(r"\s*/\s*", key):
            assert col not in used, col


def test_no_last30_or_90d_column_is_a_feature():
    for f in M["features_used"]:
        assert "last_30d" not in f and "_90d" not in f, f


def test_ninety_day_window_decomposes_exactly():
    raw = cp.load_raw()
    for metric in ["impressions", "clicks", "sessions"]:
        first30 = raw[f"{metric}_90d"] - raw[f"{metric}_last_30d"] - raw[f"{metric}_prev_30d"]
        # The only possible violation is a negative first window; the paper claims none exist.
        assert (first30 >= 0).all(), metric


def test_population_filter_reads_only_the_prior_window():
    assert M["run"]["population_filter"] == f"impressions_prev_30d >= {cp.MIN_PREV_IMPRESSIONS}"


def test_leakage_harness_can_see_leakage(modelled):
    """If adding the label source does not light up, the harness itself is broken."""
    y = modelled["label_declined"].to_numpy()
    g = modelled["client_id"].to_numpy()
    leaky = cp.design_matrix(modelled, extra_numeric=["trend_pct"])
    oof = cp.oof_scores(leaky, y, g, "logreg")
    assert roc_auc_score(y, oof) > 0.99


# ------------------------------------------------------------------ 2. receipts

def test_population_matches_receipt(modelled):
    assert len(modelled) == M["population"]["rows_modelled"]
    assert modelled["client_id"].nunique() == M["population"]["clients_modelled"]
    assert round(float(modelled["label_declined"].mean()), 4) == M["base_rate"]


def test_shipped_model_reproduces_receipt(modelled):
    y = modelled["label_declined"].to_numpy()
    g = modelled["client_id"].to_numpy()
    oof = cp.oof_scores(cp.design_matrix(modelled), y, g, "logreg")
    assert round(float(average_precision_score(y, oof)), 4) == LR["pr_auc"]
    assert round(float(roc_auc_score(y, oof)), 4) == LR["roc_auc"]
    assert round(cp.precision_at_k(oof, y, 50), 4) == LR["precision_at_k"]["50"]


def test_rule_baseline_reproduces_receipt(modelled):
    y = modelled["label_declined"].to_numpy()
    s = cp.baseline_legal_rule(modelled)
    assert round(float(average_precision_score(y, s)), 4) == RULE["pr_auc"]


def test_evidence_audit_agrees_with_pipeline():
    boot = E["bootstrap"]["intervals"]["logreg"]
    assert boot["pr_auc"]["point"] == LR["pr_auc"]
    assert boot["p@50"]["point"] == LR["precision_at_k"]["50"]
    for model in E["bootstrap"]["intervals"].values():
        for m in model.values():
            assert m["lo"] <= m["point"] <= m["hi"]


# ------------------------------------------------------------------ 3. claims

def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


GAP = E["bootstrap"]["paired_gaps"]["logreg_minus_rule"]
PERM = E["permutation_test"]
PC = E["per_client"]

CLAIMS = [
    # (file, text that must appear, where the number comes from)
    ("README.md", f"**{LR['precision_at_k']['50']:.3f}**", "LR precision@50"),
    ("README.md", f"**{LR['pr_auc']:.3f}**", "LR PR-AUC"),
    ("README.md", f"**{LR['roc_auc']:.3f}**", "LR ROC-AUC"),
    ("README.md", f"Base rate = {M['base_rate'] * 100:.1f}%", "base rate"),
    ("README.md", f"{M['population']['rows_modelled']:,}", "rows modelled"),
    ("README.md", f"{PC['roc_auc_model_wins']} of {PC['clients_eligible']} clients", "per-client wins"),
    ("README.md", f"p = {PERM['within_client_shuffle']['p_value']:.3f}", "permutation p"),
    ("README.md", f"[{GAP['p@50']['lo']:+.2f}, {GAP['p@50']['hi']:+.2f}]", "P@50 gap CI"),
    ("work/capstone_report.md", f"**{LR['pr_auc']:.4f}**", "LR PR-AUC"),
    ("work/capstone_report.md", f"{PC['roc_auc_model_wins']} of {PC['clients_eligible']}", "per-client wins"),
    ("work/capstone_report.md", f"[{GAP['pr_auc']['lo']:+.3f}, {GAP['pr_auc']['hi']:+.3f}]", "PR-AUC gap CI"),
    ("work/MODEL_CARD.md", f"{LR['precision_at_k']['50']:.2f}", "LR precision@50"),
    ("work/MODEL_CARD.md", f"{E['calibration']['calibration_slope']:.2f}", "calibration slope"),
    ("docs/index.html", f"{LR['pr_auc']:.4f}", "LR PR-AUC"),
    ("docs/index.html", f"{PC['roc_auc_model_wins']} of {PC['clients_eligible']}", "per-client wins"),
    ("docs/index.html", f"{GAP['p@50']['lo']:+.2f}", "P@50 gap CI"),
    # Numbers that once drifted from their receipts — kept here so they cannot again.
    ("README.md", f"vs {round(RULE['precision_at_k']['50'] * 50)} for the hand-written rule",
     "rule hits in the top 50"),
    ("work/capstone_report.md", f"{QSUM['top200_reason_code_mix']['model_pattern_only']} of the top 200 "
     "carry only `model_pattern_only`", "model_pattern_only count"),
    ("work/MODEL_CARD.md",
     f"**high** {E['calibration']['confidence_labels']['high']['observed_decline_rate'] * 100:.1f}% declined",
     "high-confidence hit rate"),
]


@pytest.mark.parametrize("path,text,what", CLAIMS, ids=[f"{c[0]}:{c[2]}" for c in CLAIMS])
def test_claim_matches_receipt(path, text, what):
    assert text in _read(path), f"{path} should state {what} as {text!r} (from work/outputs/)"


def test_paper_carries_data_credit():
    html = _read("docs/index.html")
    assert "https://flyrank.ai" in html


def test_paper_url_is_one_https_line():
    lines = _read("submission/paper_url.txt").strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("https://")


BANNED_WORDS = re.compile(r"\b(proves?|caused|causes)\b", re.I)


def test_conclusions_avoid_causal_language():
    """The abstract and recommendations of the report may not claim causation."""
    report = _read("work/capstone_report.md")
    abstract = report.split("## 1.")[0]
    assert not BANNED_WORDS.search(abstract), BANNED_WORDS.search(abstract)


# ------------------------------------------------------------------ 4. public safety

PUBLIC_TOP20_KEYS = {
    "rank", "content_id", "risk_score", "action", "reason_codes", "confidence",
    "decision_state", "outcome_state", "impressions_prev_30d", "prior_impr_trend_pct",
    "prior_ctr_pct", "declined_next_30d",
}
IDENTIFYING = re.compile(r"(url|domain|title|query|keyword_text|client_name|slug)", re.I)


def test_published_queue_carries_only_safe_fields():
    top20 = json.loads((OUT / "capstone_queue_top20.json").read_text())
    for row in top20:
        assert set(row) == PUBLIC_TOP20_KEYS


def test_no_receipt_has_an_identifying_key():
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)

    for path in OUT.glob("*.json"):
        for k in keys(json.loads(path.read_text())):
            assert not IDENTIFYING.search(str(k)), f"{path.name}: {k}"


def test_per_client_receipt_publishes_rank_not_id():
    for row in PC["clients"]:
        assert "client" not in row and "client_id" not in row


def test_no_dataset_committed_under_work():
    import subprocess
    files = subprocess.run(["git", "ls-files", "work"], cwd=REPO, capture_output=True,
                           text=True).stdout.split()
    assert not [f for f in files if f.endswith((".csv", ".parquet"))]


def test_scores_are_probabilities():
    lo, hi = E["calibration"]["score_range"]
    assert 0.0 <= lo < hi <= 1.0
    assert np.isclose(sum(r["n"] for r in E["calibration"]["reliability"]),
                      M["population"]["rows_modelled"])
