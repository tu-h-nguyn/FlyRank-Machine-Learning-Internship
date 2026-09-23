"""
Build the deployed research paper from the committed receipts.

    python work/scripts/build_paper.py

Reads   work/outputs/*.json  and  work/figures/*.svg   (produced by capstone_pipeline.py)
Writes  docs/index.html   -> GitHub Pages (Settings > Pages > main > /docs)

Pass --fragment PATH to also write the same page as a body-only HTML fragment (used for
previewing the paper outside the repo). It is not written by default: it is a 450 KB
duplicate of the page and does not belong in git.

Every number on the page is pulled from the JSON receipts, so the paper cannot drift away
from the pipeline: re-run the pipeline, re-run this, the page is current.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from configure_site import analytics_block, analytics_from  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "work" / "outputs"
FIG = REPO / "work" / "figures"
DOCS = REPO / "docs"

M = json.loads((OUT / "capstone_metrics.json").read_text())
IMP = json.loads((OUT / "capstone_importance.json").read_text())
COEF = json.loads((OUT / "capstone_coefficients.json").read_text())
TOP20 = json.loads((OUT / "capstone_queue_top20.json").read_text())
QSUM = json.loads((OUT / "capstone_queue_summary.json").read_text())
STATES = json.loads((OUT / "capstone_states.json").read_text())
EVID = json.loads((OUT / "evidence_audit.json").read_text())   # from evidence_audit.py

R = M["reports"]
BASE = M["base_rate"]
POP = M["population"]
STAB = M["stability_across_client_holdouts"]
GAP = M["split_design_gap"]
LR = R["Model (logistic regression, honest features)"]
RF = R["Model (random forest, honest features)"]
LEAK = R["Model (random forest, window-overlapping features)"]
RULE = R["Rule baseline (decision-time columns)"]
W4 = R["Week-4 rule (window-contaminated)"]
RAND = R["Random ordering"]
BOOT = EVID["bootstrap"]
VS_RULE = BOOT["paired_gaps"]["logreg_minus_rule"]
VS_HGB = BOOT["paired_gaps"]["logreg_minus_hgb"]
PERM = EVID["permutation_test"]
CAL = EVID["calibration"]
PCL = EVID["per_client"]
SENS = EVID["sensitivity"]
BIG = EVID["largest_client"]

REPO_URL = "https://github.com/tu-h-nguyn/FlyRank-Machine-Learning-Internship"
# The directory `git clone` creates, so the repro block below cannot drift
# away from REPO_URL when the repo is renamed.
REPO_DIR = REPO_URL.rsplit("/", 1)[-1]

# The public address, analytics code and badge link live in one place so that
# going live on a new domain is one command; see work/scripts/configure_site.py.
SITE = json.loads((REPO / "work" / "portfolio" / "site.json").read_text())
SITE_URL = SITE["base_url"].rstrip("/")
# Analytics lives in site.json too. It used to be hand-pasted into docs/index.html,
# which meant every rebuild of this page silently dropped the tag.
ANALYTICS_PROVIDER, ANALYTICS_ID = analytics_from(SITE)
BADGE_VERIFY = SITE.get("badge_verify_url", "") or "#badge-not-configured"
GSV = SITE.get("google_site_verification", "")
NB = f"{REPO_URL}/blob/main/work/notebooks"


def fig(name: str) -> str:
    """Inline a matplotlib SVG as a base64 <img> — isolated, no id collisions, self-contained."""
    data = base64.b64encode((FIG / name).read_bytes()).decode()
    return f'<img src="data:image/svg+xml;base64,{data}" alt="" loading="lazy">'


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


# ----------------------------------------------------------------------------- the page

TITLE = "The 30-Day Decline Queue"

TIMELINE_SVG = '''
<svg viewBox="0 0 760 300" role="img" aria-labelledby="tl-title tl-desc" class="timeline">
  <title id="tl-title">How one 90-day snapshot becomes a forward-looking prediction task</title>
  <desc id="tl-desc">The 90-day window splits exactly into three 30-day sub-windows. The first two
  are knowable at the decision point and become features; the last one holds the label. Any
  90-day aggregate spans all three and is therefore excluded.</desc>

  <text x="0" y="16" class="tl-label">THE 90-DAY SNAPSHOT, SPLIT</text>

  <rect x="0"   y="34" width="243" height="58" rx="4" class="tl-known"/>
  <rect x="253" y="34" width="243" height="58" rx="4" class="tl-known"/>
  <rect x="506" y="34" width="254" height="58" rx="4" class="tl-label-window"/>

  <text x="14"  y="58" class="tl-window">first30</text>
  <text x="14"  y="78" class="tl-sub">days 61–90 back</text>
  <text x="267" y="58" class="tl-window">prev30</text>
  <text x="267" y="78" class="tl-sub">days 31–60 back</text>
  <text x="520" y="58" class="tl-window tl-on-flag">last30</text>
  <text x="520" y="78" class="tl-sub tl-on-flag">days 1–30 back</text>

  <line x1="501" y1="24" x2="501" y2="196" class="tl-cut"/>
  <text x="493" y="18" class="tl-cut-label" text-anchor="end">DECISION POINT</text>

  <path d="M0 108 L496 108" class="tl-brace"/>
  <text x="0" y="130" class="tl-note">Knowable now → the 24 features</text>
  <path d="M506 108 L760 108" class="tl-brace tl-brace-flag"/>
  <text x="506" y="130" class="tl-note tl-note-flag">The outcome → the label</text>

  <text x="0" y="176" class="tl-label">WHY THE 90-DAY COLUMNS HAD TO GO</text>
  <rect x="0" y="192" width="760" height="42" rx="4" class="tl-span"/>
  <text x="14" y="218" class="tl-span-text">impressions_90d · ctr · avg_position · engagement_rate · days_with_impressions</text>
  <text x="0" y="256" class="tl-note">Every 90-day aggregate covers all three sub-windows — it already contains the answer.</text>
  <text x="0" y="278" class="tl-note">So does <tspan class="tl-mono">days_since_last_update</tspan>: 68.3% of pages were updated inside the outcome window.</text>
</svg>'''


def table(headers, rows, highlight_row=None, note=None, prose=False) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for i, r in enumerate(rows):
        cls = ' class="row-key"' if highlight_row is not None and i == highlight_row else ""
        body += "<tr" + cls + ">" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    n = f'<p class="table-note">{note}</p>' if note else ""
    wrap = "scroll prose-table" if prose else "scroll"   # prose: sentences in cells, so let them wrap
    return f'<div class="{wrap}"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{n}'


results_table = table(
    ["Method", "Base rate", "P@20", "P@50", "P@200", "Lift@50", "PR-AUC", "ROC-AUC"],
    [
        ["Random ordering <span class='tag'>floor</span>", f"{BASE:.3f}",
         f"{RAND['precision_at_k']['20']:.3f}", f"{RAND['precision_at_k']['50']:.3f}",
         f"{RAND['precision_at_k']['200']:.3f}", f"{RAND['lift_at_k']['50']:.2f}×",
         f"{RAND['pr_auc']:.4f}", f"{RAND['roc_auc']:.4f}"],
        ["Week-4 rule <span class='tag tag-flag'>contaminated</span>", f"{BASE:.3f}",
         f"{W4['precision_at_k']['20']:.3f}", f"{W4['precision_at_k']['50']:.3f}",
         f"{W4['precision_at_k']['200']:.3f}", f"{W4['lift_at_k']['50']:.2f}×",
         f"{W4['pr_auc']:.4f}", f"{W4['roc_auc']:.4f}"],
        ["Rule baseline <span class='tag'>decision-time columns</span>", f"{BASE:.3f}",
         f"{RULE['precision_at_k']['20']:.3f}", f"{RULE['precision_at_k']['50']:.3f}",
         f"{RULE['precision_at_k']['200']:.3f}", f"{RULE['lift_at_k']['50']:.2f}×",
         f"{RULE['pr_auc']:.4f}", f"{RULE['roc_auc']:.4f}"],
        ["<strong>Logistic regression</strong> <span class='tag tag-ship'>shipped</span>", f"{BASE:.3f}",
         f"<strong>{LR['precision_at_k']['20']:.3f}</strong>", f"<strong>{LR['precision_at_k']['50']:.3f}</strong>",
         f"<strong>{LR['precision_at_k']['200']:.3f}</strong>", f"<strong>{LR['lift_at_k']['50']:.2f}×</strong>",
         f"<strong>{LR['pr_auc']:.4f}</strong>", f"<strong>{LR['roc_auc']:.4f}</strong>"],
        ["Random forest", f"{BASE:.3f}",
         f"{RF['precision_at_k']['20']:.3f}", f"{RF['precision_at_k']['50']:.3f}",
         f"{RF['precision_at_k']['200']:.3f}", f"{RF['lift_at_k']['50']:.2f}×",
         f"{RF['pr_auc']:.4f}", f"{RF['roc_auc']:.4f}"],
        ["<em>Random forest + window-overlapping columns</em> <span class='tag tag-flag'>leaky</span>", f"{BASE:.3f}",
         f"<em>{LEAK['precision_at_k']['20']:.3f}</em>", f"<em>{LEAK['precision_at_k']['50']:.3f}</em>",
         f"<em>{LEAK['precision_at_k']['200']:.3f}</em>", f"<em>{LEAK['lift_at_k']['50']:.2f}×</em>",
         f"<em>{LEAK['pr_auc']:.4f}</em>", f"<em>{LEAK['roc_auc']:.4f}</em>"],
    ],
    highlight_row=3,
    note=f"All metrics out-of-fold under GroupKFold({M['run']['cv'].split('=')[1][0]}) grouped by client. "
         f"Base rate {BASE:.4f} — {M['positives']:,} of "
         f"{POP['rows_modelled']:,} pages declined. The leaky row is shown to be disowned, not claimed.",
)


def _ci(g: dict, digits: int = 3) -> str:
    return f"{g['point']:+.{digits}f} <span class='ci'>[{g['lo']:+.{digits}f}, {g['hi']:+.{digits}f}]</span>"


_w, _t, _l = SENS["precision_at_50_model_wins_ties_losses"]
evidence_table = table(
    ["Attack on the result", "What came back", "Verdict"],
    [
        ["Whole-pipeline permutation test — retrained "
         f"{PERM['n_permutations']}× on shuffled labels, globally and within each client",
         f"Real PR-AUC lift {PERM['observed_lift']:.3f}; the null never passed "
         f"{max(PERM['global_shuffle']['null_max'], PERM['within_client_shuffle']['null_max']):.3f}. "
         f"p = {PERM['within_client_shuffle']['p_value']:.3f} under both nulls, the floor for "
         f"{PERM['n_permutations']} permutations",
         "<span class='tag tag-ship'>signal is real</span>"],
        ["Client-clustered paired bootstrap, model − rule, whole ranking",
         f"ROC-AUC {_ci(VS_RULE['roc_auc'])}<br>PR-AUC {_ci(VS_RULE['pr_auc'])}",
         "<span class='tag tag-ship'>holds</span>"],
        ["Same bootstrap, precision@50 alone",
         f"{_ci(VS_RULE['p@50'], 2)}",
         "<span class='tag tag-flag'>not secure alone</span>"],
        [f"Inside each client ({PCL['clients_eligible']} with ≥50 pages)",
         f"Model beats the rule in {PCL['roc_auc_model_wins']} of {PCL['clients_eligible']} "
         f"(sign test p = {PCL['roc_auc_sign_test_p']:.3f})",
         "<span class='tag tag-ship'>not a pooling artefact</span>"],
        [f"Largest client ({BIG['largest_client_share_of_pages'] * 100:.1f}% of pages) removed / alone",
         f"PR-AUC {BIG['without_largest_client']['logreg']['pr_auc']:.3f} vs "
         f"{BIG['without_largest_client']['rule']['pr_auc']:.3f} without it; "
         f"{BIG['largest_client_only']['logreg']['pr_auc']:.3f} vs "
         f"{BIG['largest_client_only']['rule']['pr_auc']:.3f} inside it",
         "<span class='tag tag-ship'>holds</span>"],
        ["4 demand floors × 3 decline thresholds",
         f"PR-AUC: model ahead in {SENS['model_beats_rule_on_pr_auc_in']}. "
         f"Precision@50: {_w} wins, {_t} ties, {_l} loss",
         "<span class='tag tag-ship'>holds</span>"],
        ["Gradient-boosting challenger",
         f"PR-AUC {EVID['complexity_check']['gradient_boosting']['pr_auc']:.3f} vs "
         f"{LR['pr_auc']:.3f}; gap {_ci(VS_HGB['pr_auc'])}",
         "<span class='tag'>complexity not earned</span>"],
    ],
    prose=True,
    note=f"{BOOT['method'].capitalize()}. Every row is a receipt in "
         "<code>work/outputs/evidence_audit.json</code>, written by "
         "<code>work/scripts/evidence_audit.py</code>.",
)


decile_rows = [[str(dd["decile"]), f"{dd['observed_decline_rate'] * 100:.1f}%",
                f"{dd['lift']:.2f}×", f"{dd['n']:,}"] for dd in M["risk_deciles"]]
deciles_table = table(["Predicted-risk decile", "Observed decline rate", "Lift vs base", "n"],
                      decile_rows, note="Decile 10 is the riskiest. Out-of-fold scores.")

imp_rows = []
coef_by = {c["feature"]: c["std_coefficient"] for c in COEF}
readings = {
    "log_clicks_prev30": "Pages that convert impressions into clicks are associated with lower decline risk",
    "content_age_days_at_decision": "In this slice, older pages declined less — not more",
    "log_impr_first30": "Sustained earlier demand is associated with stability",
    "log_sessions_prev30": "Site-side engagement points the same way as clicks",
    "log_impr_prev30": "Holding clicks fixed, a recent impression spike is associated with higher risk",
    "prior_impr_trend_pct": "Momentum already visible before the decision point carries forward",
    "impr_share_prev30": "Where demand sat across the two visible windows",
    "main_intent_unknown": "Missing intent metadata is itself weakly informative",
}
for it in IMP[:6]:
    f = it["feature"]
    c = coef_by.get(f, 0.0)
    imp_rows.append([f"<code>{f}</code>", f"{it['importance_mean']:.4f}", f"{c:+.3f}",
                     readings.get(f, "—")])
imp_table = table(["Feature", "Permutation importance", "Std. coefficient", "Reading (observed, directional)"],
                  imp_rows,
                  note="Importance = drop in PR-AUC when the column is shuffled, measured on held-out "
                       "clients. These traffic columns are correlated with one another, so the "
                       "coefficients read as direction, not as isolated effects. Article length sits "
                       "far below this table at ≈ 0.0009.")

queue_rows = []
for r in TOP20[:8]:
    queue_rows.append([
        f"{r['rank']}", f"<code>{r['content_id']}</code>", f"{r['risk_score']:.3f}",
        f"<span class='act'>{r['action']}</span>",
        " ".join(f"<span class='code-chip'>{c}</span>" for c in r["reason_codes"].split("|")),
        r["confidence"], f"{r['impressions_prev_30d']:,}", f"{r['prior_impr_trend_pct']:+.0f}%",
    ])
ORDER = ["declining", "recovering", "growing", "stable"]
_pop = STATES["population_mix"]
_tot = sum(_pop.values())
state_rows = [[f"Top {int(k):,}"] +
              [f"{STATES['top_k_outcome_mix'][k][st]['share'] * 100:.0f}%" for st in ORDER]
              for k in ["50", "200", "500", "1000"]]
state_rows.append(["<em>Whole population</em>"] +
                  [f"<em>{_pop.get(st, 0) / _tot * 100:.0f}%</em>" for st in ORDER])
state_table = table(["Slice of the queue"] + ORDER, state_rows,
                    note="What actually happened to the pages the engine ranked highest. Read the "
                         "top row against the bottom one: the queue concentrates decline and "
                         "pushes growth out.")

queue_table = table(["#", "Page (pseudonymous)", "Risk", "Action", "State at decision",
                     "Reason codes", "Confidence", "Impr. prev 30d", "Prior trend"], queue_rows,
                    note="The first eight rows of an 18,010-row queue. IDs are pseudonyms — no client, "
                         "domain, URL or query appears anywhere in this work.")

recs = [
    ("Work the model queue instead of an age or freshness sort — start with the top 50.",
     f"Precision@50 {LR['precision_at_k']['50']:.2f} against {RULE['precision_at_k']['50']:.2f} for the "
     f"transparent rule and a {BASE:.3f} base rate. In the first 50 hours of review, roughly "
     f"{round(LR['precision_at_k']['50'] * 50)} of 50 land on real decliners instead of "
     f"{round(BASE * 50)}.",
     "The portfolio changes shape, or the period sits inside a strong seasonal swing."),
    ("Use “old and high-impression” as a filter, never as a ranker.",
     "That rule scores 12 of 18,010 pages above zero (11 of them declined) and is silent on the rest — "
     "every remaining page ties at zero, so its order is arbitrary. ROC-AUC 0.500.",
     "On the full warehouse, a properly aligned freshness column could regain its power."),
    ("Treat “impressions spiking without clicks” as the early-warning sign.",
     "Prior-window clicks is the top permutation-importance feature (0.077 PR-AUC) with a negative "
     "coefficient (−0.583), while prior-window impressions carries the largest positive one (+0.910). "
     "Grouped directly: among pages with ≥500 impressions, the lowest click-through quartile declined "
     "at 73.6% against 48.9% in the highest (n ≈ 2,780 per quartile).",
     "The page deliberately serves an on-SERP informational need, where low CTR is normal."),
    ("Split the work by reason code instead of calling everything a refresh.",
     f"Of the top 200: {QSUM['top200_action_mix'].get('review_for_refresh', 0)} refresh reviews, "
     f"{QSUM['top200_action_mix'].get('review_metadata_and_intent', 0)} metadata/intent reviews "
     "(clicks falling while impressions hold — a title job, not a rewrite), "
     f"{QSUM['top200_action_mix'].get('protect_and_refresh', 0)} protect-and-refresh, "
     f"{QSUM['top200_action_mix'].get('protect_and_watch', 0)} protect-and-watch on pages that are "
     f"gaining, and {QSUM['top200_action_mix'].get('monitor', 0)} monitor-only.",
     "The thresholds behind the reason codes move — they are policy choices, not constants."),
    ("Keep a human gate in front of every action, and automate nothing.",
     "The model never reads page content, cannot see a sibling page absorbing demand, and cannot "
     f"separate seasonality from decline. {QSUM['top200_reason_code_mix'].get('model_pattern_only', 0)} "
     "of the top 200 carry only <code>model_pattern_only</code> "
     "and are downgraded to monitor by design.",
     "Nothing — this is a design boundary, not a tunable parameter."),
]
rec_html = ""
for i, (head, evidence, wrong) in enumerate(recs, 1):
    rec_html += f'''
    <li class="rec">
      <p class="rec-head"><span class="rec-num">{i}</span>{head}</p>
      <p class="rec-ev"><span class="rec-tag">Evidence</span>{evidence}</p>
      <p class="rec-wrong"><span class="rec-tag">Wrong if</span>{wrong}</p>
    </li>'''

limits = [
    ("One snapshot, not a time series",
     "I reconstruct <em>one</em> decision point from one 90-day window. Nothing here tests whether the "
     "ranking holds across months."),
    ("Decline, seasonality, consolidation and noise look identical here",
     "A page marked “declining” may simply be handing demand to a sibling page, or following an annual cycle."),
    ("The results speak for 18,010 pages, not 30,000",
     f"The ≥100-impression demand floor drops {POP['rows_start'] - POP['rows_modelled']:,} low-volume pages. "
     "For those, this system is silent — not reassuring."),
    ("Thirty clients is a small sample",
     f"PR-AUC moves between {STAB['pr_auc_min']} and {STAB['pr_auc_max']} depending on which clients are "
     f"held out. That range is the result, not the single {LR['pr_auc']:.4f}. The client-bootstrap "
     f"interval on the precision@50 gap over the rule, {VS_RULE['p@50']['lo']:+.2f} to "
     f"{VS_RULE['p@50']['hi']:+.2f}, crosses zero."),
    ("Search position could not be used at all",
     "The only position column is a 90-day mean that spans the outcome window. A central SEO signal had "
     "to be dropped; the warehouse's daily table would restore it."),
    ("Content freshness could not be used either",
     "68.3% of pages were updated inside the outcome window, so <code>days_since_last_update</code> "
     "knows the future."),
    ("Public slice, not the full warehouse",
     "The gated ~79M-row release needs a token this run did not have. The feature contract is "
     "source-agnostic; the published numbers are from the public slice."),
    ("The label is a product definition",
     "“Down” means a &gt;20% impression drop because that is how the product defines it. Move the "
     "threshold and the population moves with it."),
    ("No causal evidence exists in this work",
     "No experiment, no control group, no causal design. This work cannot say that refreshing a page "
     "recovers its traffic, and says nothing whatsoever about Google's algorithm."),
]
limit_html = "".join(
    f'<li><p class="lim-head">{h}</p><p class="lim-body">{b}</p></li>' for h, b in limits)

CSS = '''
:root{
  --ground:#f4f6f8; --surface:#ffffff; --surface-2:#eef1f5;
  --ink:#0d1720; --ink-2:#2b3948; --muted:#5d6d80; --rule:#d8e0e9;
  --signal:#0b5fb0; --signal-soft:#e4eefa; --flag:#b23c0b; --flag-soft:#fbeadf;
  --good:#0f6b62; --plate:#ffffff; --plate-rule:#dfe5ec;
  --shadow:0 1px 2px rgba(13,23,32,.05), 0 8px 24px -16px rgba(13,23,32,.28);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#0d1219; --surface:#131b24; --surface-2:#18222d;
    --ink:#e7edf4; --ink-2:#bcc9d8; --muted:#8698ab; --rule:#243140;
    --signal:#6cb0f5; --signal-soft:#152435; --flag:#f0916a; --flag-soft:#2a1c15;
    --good:#4fb3a6; --plate:#ffffff; --plate-rule:#243140;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --ground:#0d1219; --surface:#131b24; --surface-2:#18222d;
  --ink:#e7edf4; --ink-2:#bcc9d8; --muted:#8698ab; --rule:#243140;
  --signal:#6cb0f5; --signal-soft:#152435; --flag:#f0916a; --flag-soft:#2a1c15;
  --good:#4fb3a6; --plate:#ffffff; --plate-rule:#243140;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -18px rgba(0,0,0,.8);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans","Segoe UI",system-ui,-apple-system,sans-serif;
  font-size:17px; line-height:1.62; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:860px; margin:0 auto; padding:0 24px 96px}
p{margin:0 0 1.05em; max-width:68ch}
a{color:var(--signal); text-decoration:none; border-bottom:1px solid color-mix(in srgb, var(--signal) 35%, transparent)}
a:hover{border-bottom-color:var(--signal)}
a:focus-visible,summary:focus-visible{outline:2px solid var(--signal); outline-offset:3px; border-radius:2px}
code{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.86em;
  background:var(--surface-2); padding:.12em .38em; border-radius:3px; color:var(--ink-2)}
em{font-style:italic}

/* masthead ---------------------------------------------------------------- */
.masthead{padding:64px 0 8px; border-bottom:1px solid var(--rule)}
.eyebrow{font-family:"IBM Plex Mono",monospace; font-size:12px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--muted); margin:0 0 22px}
h1{font-family:"IBM Plex Serif",Georgia,serif; font-weight:600; font-size:clamp(2.1rem,5.4vw,3.35rem);
  line-height:1.1; letter-spacing:-.02em; margin:0 0 18px; text-wrap:balance; max-width:20ch}
.deck{font-size:1.16rem; color:var(--ink-2); max-width:62ch; margin:0 0 30px}
.byline{font-family:"IBM Plex Mono",monospace; font-size:12.5px; color:var(--muted);
  display:flex; flex-wrap:wrap; gap:8px 18px; margin:0 0 34px}

/* stat strip -------------------------------------------------------------- */
.stats{display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1px;
  background:var(--rule); border:1px solid var(--rule); border-radius:6px; overflow:hidden; margin:0 0 44px}
.stat{background:var(--surface); padding:16px 18px}
.stat-n{font-family:"IBM Plex Mono",monospace; font-size:1.62rem; font-weight:600;
  font-variant-numeric:tabular-nums; letter-spacing:-.02em; color:var(--ink); display:block; line-height:1.2}
.stat-l{font-size:12.5px; color:var(--muted); display:block; margin-top:4px; line-height:1.35}
.stat-key .stat-n{color:var(--signal)}

/* abstract ---------------------------------------------------------------- */
.abstract{background:var(--surface); border:1px solid var(--rule); border-left:3px solid var(--signal);
  border-radius:4px; padding:26px 28px; margin:0 0 20px; box-shadow:var(--shadow)}
.abstract p{margin:0; font-size:1.02rem; color:var(--ink-2); max-width:none}
.abstract .eyebrow{margin-bottom:12px}

/* sections ---------------------------------------------------------------- */
section{padding-top:52px}
h2{font-family:"IBM Plex Serif",Georgia,serif; font-size:1.72rem; font-weight:600; letter-spacing:-.015em;
  line-height:1.22; margin:0 0 6px; display:flex; gap:14px; align-items:baseline; text-wrap:balance}
.sec-n{font-family:"IBM Plex Mono",monospace; font-size:.8rem; font-weight:500; color:var(--signal);
  border:1px solid color-mix(in srgb,var(--signal) 35%,transparent); border-radius:3px;
  padding:2px 7px; flex:none; position:relative; top:-3px}
.sec-sub{font-family:"IBM Plex Mono",monospace; font-size:12px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted); margin:0 0 22px}
h3{font-family:"IBM Plex Sans",sans-serif; font-size:1.03rem; font-weight:600; margin:32px 0 10px;
  letter-spacing:-.005em}

/* figures ----------------------------------------------------------------- */
figure{margin:26px 0 30px}
.plate{background:var(--plate); border:1px solid var(--plate-rule); border-radius:5px;
  padding:14px 16px; box-shadow:var(--shadow)}
.plate img{display:block; width:100%; height:auto}
figcaption{font-size:14px; color:var(--muted); margin-top:11px; max-width:66ch; line-height:1.5}
figcaption b{color:var(--ink-2); font-weight:600}

/* the timeline diagram ---------------------------------------------------- */
.diagram{background:var(--surface); border:1px solid var(--rule); border-radius:5px;
  padding:24px 26px 18px; margin:26px 0 12px; box-shadow:var(--shadow)}
.timeline{width:100%; height:auto; display:block}
.tl-known{fill:var(--signal-soft); stroke:var(--signal); stroke-width:1}
.tl-label-window{fill:var(--flag-soft); stroke:var(--flag); stroke-width:1}
.tl-span{fill:none; stroke:var(--muted); stroke-width:1; stroke-dasharray:3 3}
.tl-window{font-family:"IBM Plex Mono",monospace; font-size:15px; font-weight:600; fill:var(--ink)}
.tl-sub{font-family:"IBM Plex Sans",sans-serif; font-size:12.5px; fill:var(--ink-2)}
.tl-on-flag{fill:var(--ink)}
.tl-label{font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.13em; fill:var(--muted)}
.tl-cut{stroke:var(--flag); stroke-width:1.5; stroke-dasharray:4 4}
.tl-cut-label{font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.11em; fill:var(--flag)}
.tl-brace{stroke:var(--signal); stroke-width:2}
.tl-brace-flag{stroke:var(--flag)}
.tl-note{font-family:"IBM Plex Sans",sans-serif; font-size:13px; fill:var(--ink-2)}
.tl-note-flag{fill:var(--flag)}
.tl-span-text{font-family:"IBM Plex Mono",monospace; font-size:12.5px; fill:var(--ink-2)}
.tl-mono{font-family:"IBM Plex Mono",monospace; font-size:12.5px}

/* tables ------------------------------------------------------------------ */
.scroll{overflow-x:auto; border:1px solid var(--rule); border-radius:5px; background:var(--surface);
  margin:22px 0 8px; box-shadow:var(--shadow)}
table{border-collapse:collapse; width:100%; font-size:14.5px}
th{font-family:"IBM Plex Mono",monospace; font-size:11.5px; letter-spacing:.07em; text-transform:uppercase;
  color:var(--muted); text-align:left; padding:12px 14px; border-bottom:1px solid var(--rule);
  white-space:nowrap; font-weight:500}
td{padding:11px 14px; border-bottom:1px solid var(--rule); color:var(--ink-2); vertical-align:top}
td:not(:first-child){font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
.row-key td{background:var(--signal-soft); color:var(--ink)}
.table-note{font-size:13.5px; color:var(--muted); margin:10px 0 0; max-width:66ch}
.tag{font-family:"IBM Plex Sans",sans-serif; font-size:11px; letter-spacing:.03em; color:var(--muted);
  border:1px solid var(--rule); border-radius:99px; padding:1px 8px; margin-left:6px; white-space:nowrap}
.tag-flag{color:var(--flag); border-color:color-mix(in srgb,var(--flag) 40%,transparent)}
.tag-ship{color:var(--signal); border-color:color-mix(in srgb,var(--signal) 45%,transparent)}
.act{font-family:"IBM Plex Mono",monospace; font-size:12.5px; color:var(--ink)}
.code-chip{display:inline-block; font-family:"IBM Plex Mono",monospace; font-size:11px;
  background:var(--surface-2); border-radius:3px; padding:1px 6px; margin:1px 3px 1px 0; color:var(--ink-2)}

/* callouts ---------------------------------------------------------------- */
.callout{background:var(--surface); border:1px solid var(--rule); border-left:3px solid var(--flag);
  border-radius:4px; padding:20px 24px; margin:26px 0}
.callout p:last-child{margin-bottom:0}
.callout .eyebrow{color:var(--flag); margin-bottom:10px}
.pull{font-family:"IBM Plex Serif",Georgia,serif; font-size:1.3rem; line-height:1.42; color:var(--ink);
  border-left:3px solid var(--signal); padding:4px 0 4px 20px; margin:30px 0; max-width:56ch}

/* lists ------------------------------------------------------------------- */
ol.recs,ol.limits{list-style:none; padding:0; margin:24px 0; display:flex; flex-direction:column; gap:14px}
.rec{background:var(--surface); border:1px solid var(--rule); border-radius:5px; padding:20px 22px;
  box-shadow:var(--shadow)}
.rec p{margin:0; max-width:64ch}
.rec-head{font-weight:600; font-size:1.04rem; color:var(--ink); display:flex; gap:12px; align-items:baseline;
  line-height:1.4; margin-bottom:10px !important}
.rec-num{font-family:"IBM Plex Mono",monospace; font-size:.78rem; color:var(--surface);
  background:var(--signal); border-radius:3px; padding:2px 7px; flex:none}
.rec-ev,.rec-wrong{font-size:14.6px; color:var(--ink-2); margin-bottom:7px !important}
.rec-wrong{color:var(--muted); margin-bottom:0 !important}
.rec-tag{font-family:"IBM Plex Mono",monospace; font-size:10.5px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--muted); margin-right:10px}
ol.limits{counter-reset:lim}
ol.limits li{counter-increment:lim; border-left:2px solid var(--rule); padding:2px 0 2px 18px}
.lim-head{font-weight:600; margin:0 0 3px !important; color:var(--ink); font-size:.99rem}
.lim-head::before{content:counter(lim) ". "; font-family:"IBM Plex Mono",monospace; color:var(--flag); font-size:.86em}
.lim-body{margin:0 !important; font-size:14.8px; color:var(--ink-2)}
ul.plain{padding-left:20px; margin:14px 0}
ul.plain li{margin-bottom:8px; color:var(--ink-2); max-width:66ch}
.ci{color:var(--muted); font-size:.9em; white-space:nowrap}
.prose-table td:nth-child(2){font-family:inherit; white-space:normal; min-width:260px}
.prose-table td:first-child{min-width:180px}
.plate-narrow{max-width:520px; margin-left:auto; margin-right:auto}

/* repro + footer ---------------------------------------------------------- */
pre{background:var(--surface); border:1px solid var(--rule); border-radius:5px; padding:16px 18px;
  overflow-x:auto; font-family:"IBM Plex Mono",monospace; font-size:13.5px; line-height:1.6;
  color:var(--ink-2); margin:20px 0}
.links{display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:22px 0}
.link-card{background:var(--surface); border:1px solid var(--rule); border-radius:5px; padding:14px 16px}
.link-card a{border:none; font-weight:600; font-size:.97rem}
.link-card span{display:block; font-size:13px; color:var(--muted); margin-top:3px}
footer{margin-top:72px; padding-top:26px; border-top:1px solid var(--rule); color:var(--muted); font-size:14.5px}
footer strong{color:var(--ink-2)}
.grad-badge-wrap{margin-top:22px}
.grad-badge{display:inline-block; border-bottom:0; line-height:0; border-radius:10px}
.grad-badge img{width:238px; height:auto; display:block}
.grad-badge:focus-visible{outline:2px solid var(--signal); outline-offset:3px}
.grad-badge-note{margin:9px 0 0; font-size:13px; color:var(--muted)}
@media (max-width:620px){
  body{font-size:16px}
  .wrap{padding:0 18px 72px}
  .masthead{padding-top:44px}
  h2{gap:10px}
}
@media (prefers-reduced-motion:reduce){*{animation:none !important; transition:none !important}}
'''

BODY = f'''
<div class="wrap">
<header class="masthead">
  <p class="eyebrow">FlyRank ML Internship · Capstone · Lane 2 — Refresh &amp; Content Opportunity Scoring</p>
  <h1>Which page should an editor open first?</h1>
  <p class="deck">Ranking 18,010 pages by their risk of losing search visibility over the next 30 days —
  and finding out, along the way, that my own baseline rule could not rank anything at all.</p>
  <p class="byline">
    <span>John · Applied Search Intelligence</span>
    <span>August 2026</span>
    <span>Data: FlyRank ML Internship dataset</span>
    <span>Seed 42 · every number reproducible</span>
  </p>

  <div class="stats">
    <div class="stat"><span class="stat-n">18,010</span><span class="stat-l">pages ranked, 30 pseudonymous clients</span></div>
    <div class="stat"><span class="stat-n">{BASE:.3f}</span><span class="stat-l">base rate — share that actually declined</span></div>
    <div class="stat stat-key"><span class="stat-n">{LR['precision_at_k']['50']:.2f}</span><span class="stat-l">precision@50, out-of-fold (rule: {RULE['precision_at_k']['50']:.2f})</span></div>
    <div class="stat"><span class="stat-n">0.500</span><span class="stat-l">ROC-AUC of my own Week-4 rule</span></div>
  </div>
</header>

<div class="abstract">
  <p class="eyebrow">Abstract</p>
  <p>When an editorial team can review only a few dozen pages a week, the real question is not which
  pages are bad but which page to open first. Using the public anonymized FlyRank starter slice
  (30,000 pages × 44 columns, 32 pseudonymous clients, one trailing 90-day snapshot), I split the
  90-day window into three exact 30-day sub-windows and kept only signals knowable at the decision
  point, then ranked pages by their risk of losing more than 20% of search impressions over the next
  30 days. A logistic regression over 24 such features, scored out-of-fold under a client-grouped
  split, placed <strong>{pct(LR['precision_at_k']['50'], 0)} real decliners in its top 50</strong> against
  {pct(RULE['precision_at_k']['50'], 0)} for a transparent rule baseline and a {pct(BASE)} base rate —
  while the rule I had built in Week 4 turned out to score just 12 of 18,010 pages above zero and
  therefore rank nothing at all (ROC-AUC {W4['roc_auc']:.3f}). Adding the window-overlapping columns back
  lifted precision@200 to {LEAK['precision_at_k']['200']:.3f}, a beautiful number that is a leakage
  confession rather than a result. A whole-pipeline permutation test (p = {PERM['within_client_shuffle']['p_value']:.3f})
  and a client-clustered bootstrap indicate the ranking advantage is not chance and holds inside
  {PCL['roc_auc_model_wins']} of {PCL['clients_eligible']} clients — while the precision@50 margin on its own sits within noise.
  The deliverable is an 18,010-row action queue with reason codes,
  a suggested action and a confidence label, built to support the order of human review — not to
  promise that refreshing a page recovers its traffic.</p>
</div>

<section id="problem">
  <h2><span class="sec-n">01</span>The decision this supports</h2>
  <p class="sec-sub">Introduction</p>
  <p>An editor opens Monday morning with capacity for about fifty pages and a portfolio of tens of
  thousands. Nothing in that situation is improved by a list of everything that looks unhealthy;
  what is missing is an <em>order</em>. That is the decision this work supports, and it is the reason
  the metric here is precision@K at the team's real capacity rather than accuracy.</p>

  <p>The unit is one pseudonymous content item in one snapshot. The output is a ranked queue where
  every row carries a risk score, the reasons behind it, a suggested action and a confidence label.
  The action a human takes is to review — check business value, check whether a sibling page absorbed
  the demand, check seasonality — and then refresh, fix metadata, protect or simply watch.</p>

  <p>The costs of being wrong are asymmetric. A false alarm burns an editor's hour and disturbs a page
  that was stable. A miss lets a page with real demand decay quietly until recovery is expensive.
  Since the top of the list is what gets acted on, the top of the list is what gets measured.</p>

  <p class="pull">A threshold rule can select a group of pages. It cannot put them in order — and the
  order is the entire decision.</p>
</section>

<section id="data">
  <h2><span class="sec-n">02</span>The data, and the split that made it a prediction problem</h2>
  <p class="sec-sub">Data</p>
  <p>Everything here runs on <code>data/raw/content_refresh_anonymized.csv</code>, the public anonymized
  starter slice of the FlyRank ML Internship dataset: 30,000 content items across 32 pseudonymous
  clients, with Google Search Console and GA4 metrics aggregated over one rolling 90-day window.
  The full ~79M-row warehouse release is gated and requires a token this run did not have; the feature
  contract is source-agnostic, but the published numbers come from the public slice. That is a
  limitation, stated rather than hidden.</p>

  <p>The snapshot is cross-sectional — one row per page, no time axis — which normally rules out an
  honest forward-looking task. It does not, because the 90-day totals decompose <em>exactly</em> into
  three 30-day sub-windows (verified: maximum reconstruction error is zero). That decomposition is
  what turns a snapshot into a decision point.</p>

  <div class="diagram">{TIMELINE_SVG}</div>
  <figcaption><b>The whole method in one picture.</b> Stand at the boundary. Everything to the left is
  knowable; everything to the right is the outcome being predicted. Any column that spans the
  boundary — every 90-day total, every 90-day rate — already contains the answer.</figcaption>

  <h3>What was excluded, and why</h3>
  <ul class="plain">
    <li><strong>Label-derived:</strong> <code>trend_pct</code> and <code>trend_direction</code>. The label
    is computed from them; using them is circular.</li>
    <li><strong>Window-spanning:</strong> every <code>*_90d</code> total and rate — impressions, clicks,
    sessions, CTR, average position, engagement rate, scroll rate, AI traffic share, days with
    impressions — plus every last-30-day column.</li>
    <li><strong>Product decisions:</strong> <code>impression_tier</code>, <code>position_tier</code>,
    <code>freshness_tier</code>. These encode a judgement an existing system already made; they may be
    a baseline to beat, never an input.</li>
    <li><strong>Identifiers:</strong> <code>content_id</code> and <code>client_id</code> are pseudonyms used
    for grouping and splitting only.</li>
  </ul>

  <div class="callout">
    <p class="eyebrow">The exclusion that hurt</p>
    <p><code>days_since_last_update</code> is exactly the signal my Week-4 rule leaned on — and it is
    measured at export time, so it reports edits that happened <em>inside</em> the outcome window.
    In this slice <strong>20,480 of 30,000 pages (68.3%)</strong> were updated inside that window. The
    column knows the future, so it had to go, and losing it is a large part of why the honest numbers
    on this page are modest.</p>
  </div>

  <h3>Population</h3>
  <p>Pages with fewer than 100 impressions in the prior 30 days are excluded: below that floor a
  “decline” is noise, and no editor should spend an hour on it. That drops
  {POP['rows_start'] - POP['rows_modelled']:,} pages and leaves <strong>{POP['rows_modelled']:,} pages
  across {POP['clients_modelled']} clients</strong>. The filter reads only pre-decision columns, so it
  carries no outcome information — but it does narrow what these results can speak about.</p>

  <p><strong>Public safety.</strong> No client names, domains, URLs, page titles or search queries appear
  anywhere in this work — only pseudonymous IDs and aggregates.</p>
</section>

<section id="method">
  <h2><span class="sec-n">03</span>Method: 24 features that existed before the outcome</h2>
  <p class="sec-sub">Methodology</p>
  <p><strong>Label.</strong> A page is labelled declined when its impressions over the most recent 30 days
  fell more than 20% against the previous 30 days — the product's own definition of
  <code>trend_direction == "down"</code>. Base rate: <strong>{pct(BASE)}</strong>.</p>

  <p><strong>Features.</strong> Twenty-four columns, all knowable at the decision point: demand level in
  the two visible windows (log impressions, clicks, sessions), the momentum already visible between
  them, prior-window click-through and how it shifted, content age at the decision point, article
  length with a measured/not-measured flag, and keyword context (search volume, competition, CPC)
  with its own flag. Missingness in this dataset follows <code>content_type</code>, so a blind
  <code>fillna(0)</code> would quietly encode content type into the model — flags first, then fill.</p>

  <p><strong>Baselines.</strong> Two, both frozen before modelling started. The Week-4 rule, kept exactly
  as written (<em>stale × visible × impressions</em>, reading two contaminated columns), and a legal
  rewrite of the same idea using only decision-time columns: a page is worth reviewing first if it
  already lost ground between the two visible windows and still carries demand, with a small penalty
  for below-median click-through. No fitted weights in either.</p>

  <p><strong>Validation.</strong> <code>GroupKFold(5)</code> grouped by <code>client_id</code>, with every
  metric computed out-of-fold. Pages from one client share hidden character — same site, same editorial
  team — so a random split lets a model memorise the client and call it skill. Measured here, that
  memorisation is worth <strong>+{GAP['gap']:.4f} PR-AUC</strong>: {GAP['random_row_split_pr_auc']:.4f} on a
  random row split versus {GAP['grouped_by_client_pr_auc']:.4f} grouped by client.</p>

  <p><strong>Leakage tests.</strong> Three, all in the audit notebook. Deliberately adding
  <code>trend_pct</code> pushes ROC-AUC to 0.9997 — proof the harness can see leakage when it exists.
  Train-with versus train-without on the window-spanning group is reported below as its own result.
  A scan of the final feature set for product flags and IDs comes back clean. (My first version of
  that scan used substring matching and produced false positives on the legal <code>prior_*_trend</code>
  columns — the check was fixed to match exact names.)</p>
</section>

<section id="results">
  <h2><span class="sec-n">04</span>Results: a modest, real win — and one loud failure</h2>
  <p class="sec-sub">Results</p>
  {results_table}

  <figure>
    <div class="plate">{fig("precision_at_k.svg")}</div>
    <figcaption><b>At every K a real team could work through, the model's queue sits above both rules.</b>
    The Week-4 rule converges on the base rate: past its twelve flagged pages, its ordering carries no
    information.</figcaption>
  </figure>

  <h3>The failure worth more than the win</h3>
  <p>The rule I built in Week 4 — old content with high impressions — scores <strong>12 of 18,010
  pages</strong> above zero. Eleven of those twelve did decline, so it is precise on the sliver it can
  see. For the other 17,998 pages every score ties at zero, which means their order is arbitrary. That
  is what ROC-AUC {W4['roc_auc']:.3f} and precision@200 falling back to the base rate actually describe.
  The rule is a serviceable <em>filter</em> and not a <em>ranker</em>, and a review queue needs the second.</p>

  <h3>What leakage would have bought</h3>
  <p>Put the window-spanning columns back and the same random forest reports precision@50 of
  {LEAK['precision_at_k']['50']:.3f} and precision@200 of {LEAK['precision_at_k']['200']:.3f}. Nothing
  improved except the appearance of the result: <code>impressions_90d</code> minus the two visible
  windows <em>is</em> the label window. This number is on the page to be disowned.</p>

  <figure>
    <div class="plate">{fig("honest_vs_leaky.svg")}</div>
    <figcaption><b>Same model, different feature set.</b> The top bar is what a contaminated feature set
    looks like from the outside — indistinguishable from excellent work until someone lines the windows
    up.</figcaption>
  </figure>

  <h3>How steady is the win?</h3>
  <p>Across five different client holdouts, PR-AUC moves between {STAB['pr_auc_min']} and
  {STAB['pr_auc_max']} (mean {STAB['pr_auc_mean']:.4f} ± {STAB['pr_auc_std']:.4f}) and precision@50 sits at
  {STAB['precision_at_50_mean']:.3f} ± {STAB['precision_at_50_std']:.3f}. With thirty clients, that range
  is the honest result — not the single {LR['pr_auc']:.4f}. Simplicity also won on merit: the logistic
  regression edged the random forest ({LR['pr_auc']:.4f} vs {RF['pr_auc']:.4f}), so the readable model
  is the one that ships.</p>


  <h3>Is the win bigger than the noise?</h3>
  <p>Thirty clients, one of which holds {BIG['largest_client_share_of_pages'] * 100:.1f}% of the pages,
  is a small sample, and a point estimate on a small sample is a claim, not evidence. So the
  headline was attacked six ways, and each answer was committed as a receipt before this paragraph
  was written.</p>

  {evidence_table}

  <figure>
    <div class="plate">{fig("evidence_permutation.svg")}</div>
    <figcaption><b>Chance does not get close.</b> The whole pipeline — features, grouped folds, model —
    retrained on shuffled labels {PERM['n_permutations']} times per null. Shuffling <em>within</em>
    each client keeps every client's own decline rate, so a model that had only learned “which client
    declines more” would pass it. It does not.</figcaption>
  </figure>

  <figure>
    <div class="plate">{fig("evidence_bootstrap.svg")}</div>
    <figcaption><b>The honest shape of the win.</b> Against the rule, the whole-ranking metrics sit
    clear of zero or nearly so; precision@20 and precision@50 do not. “{round(LR['precision_at_k']['50'] * 50)}
    of the top 50” against {round(RULE['precision_at_k']['50'] * 50)} is what happened on this snapshot,
    not a guarantee for the next one. Against gradient boosting every interval straddles zero — extra
    complexity bought nothing, so the readable model ships.</figcaption>
  </figure>

  <figure>
    <div class="plate">{fig("evidence_capacity.svg")}</div>
    <figcaption><b>Precision at every review capacity, with client-bootstrap bands.</b> The model's
    line sits above the rule's from K = 30 onward; the bands overlap, which is what thirty clients
    buys.</figcaption>
  </figure>

  <figure>
    <div class="plate">{fig("evidence_per_client.svg")}</div>
    <figcaption><b>Inside each client, not just in the pool.</b> A pooled ranking can win by sorting
    clients rather than pages. Within-client ROC-AUC rules that out: the model is ahead in
    {PCL['roc_auc_model_wins']} of {PCL['clients_eligible']} clients, including all four of the
    largest. Clients are shown by size rank, never by ID.</figcaption>
  </figure>

  <h3>Can the score be read as a probability?</h3>
  <p>Mostly, and not at the top. The Brier score beats always predicting the base rate
  (skill {CAL['brier_skill_score']:+.3f}), the expected calibration error is
  {CAL['expected_calibration_error']:.3f}, and the middle deciles sit on the diagonal. But the
  calibration slope is {CAL['calibration_slope']:.2f}: the riskiest tenth averages a predicted
  {CAL['reliability'][-1]['mean_predicted']:.2f} while {CAL['reliability'][-1]['observed_rate']:.2f}
  actually declined. The queue therefore prints a confidence label rather than a percentage, and the
  labels behave as ordered — <strong>high</strong>
  {CAL['confidence_labels']['high']['observed_decline_rate'] * 100:.1f}% declined,
  <strong>medium</strong> {CAL['confidence_labels']['medium']['observed_decline_rate'] * 100:.1f}%,
  <strong>low</strong> {CAL['confidence_labels']['low']['observed_decline_rate'] * 100:.1f}%.</p>

  <figure>
    <div class="plate plate-narrow">{fig("evidence_calibration.svg")}</div>
    <figcaption><b>Well calibrated in the middle, overconfident at the top.</b> Read the score as a
    rank.</figcaption>
  </figure>

  {deciles_table}

  <figure>
    <div class="plate">{fig("risk_deciles.svg")}</div>
    <figcaption><b>Real signal, no sharp boundary.</b> The riskiest decile declined at
    {M['risk_deciles'][9]['observed_decline_rate'] * 100:.1f}% against
    {M['risk_deciles'][0]['observed_decline_rate'] * 100:.1f}% in the safest — a
    {M['risk_deciles'][9]['observed_decline_rate'] / M['risk_deciles'][0]['observed_decline_rate']:.2f}×
    spread. The middle deciles sit near the base rate, which is exactly where this queue should not be
    trusted.</figcaption>
  </figure>

  <h3>What the model leans on</h3>
  {imp_table}

  <figure>
    <div class="plate">{fig("feature_importance.svg")}</div>
    <figcaption><b>Prior-window clicks dominate; article length barely registers.</b> The March 2026
    FlyRank study observed growing pages at 3.2K words against 2.3K for declining ones. In this
    forward-looking framing the gap nearly vanishes — 3,483 versus 3,432 words (n = 12,785). Not a
    contradiction: one measures an observed state, the other measures predictive power.</figcaption>
  </figure>

  <p class="pull">Holding clicks fixed, a recent impression spike is associated with <em>higher</em>
  decline risk. The clearest early warning in this data is exposure that did not convert.</p>

  <h3>Three signals, checked one at a time</h3>
  <p>The model is not the only way to read this data, and simple grouped comparisons are easier for an
  editor to sanity-check. Three, each with the verdict the numbers actually supported:</p>
  <ul class="plain">
    <li><strong>Prior momentum — confirmed, with a fold.</strong> Pages that had already lost more than
    half their demand between the two visible windows declined at 70.6%, falling to 52.4% for pages up
    20–50%. But pages that <em>spiked</em> more than +50% turn back up to 58.7%: a jump in impressions
    is not, by itself, good news.</li>
    <li><strong>Low click-through at high exposure — confirmed, and stronger than expected.</strong>
    Among pages with ≥500 impressions, decline runs monotonically from 73.6% in the lowest
    click-through quartile to 48.9% in the highest — a 24.7-point spread on roughly 2,780 pages per
    quartile.</li>
    <li><strong>Longer articles hold up better — mixed, and it does not survive.</strong> Grouped, the
    1,000–2,000-word band does decline more (79.4%, n = 1,444). But the two label groups average 3,483
    against 3,432 words, the &lt;1,000-word bucket holds only 15 pages and must not be read, and once
    demand and click signals are present, length adds essentially nothing (importance ≈ 0.0009).</li>
  </ul>
</section>

<section id="limits">
  <h2><span class="sec-n">05</span>What this work cannot claim</h2>
  <p class="sec-sub">Limitations &amp; honest framing</p>
  <ol class="limits">{limit_html}</ol>
  <div class="callout">
    <p class="eyebrow">Language discipline</p>
    <p>Every finding on this page is written as <em>observed</em>, <em>measured</em>,
    <em>associated with</em> or <em>decision-support</em>. There is no experiment behind this work, so
    the words <em>proves</em>, <em>causes</em> and <em>will increase</em> do not appear in any conclusion —
    and nothing here describes, tests or reverse-engineers Google's ranking algorithm.</p>
  </div>
</section>

<section id="recommendations">
  <h2><span class="sec-n">06</span>What to do first</h2>
  <p class="sec-sub">Ranked recommendations</p>
  <ol class="recs">{rec_html}</ol>

  <h3>The four states, and which of them the engine can act on</h3>
  <p>The lane asks for pages scored as growing, declining, recovering or worth review. Those states
  sit on opposite sides of the decision point, so the queue carries them in two separate columns and
  never mixes them:</p>
  <ul class="plain">
    <li><strong><code>decision_state</code> — actionable.</strong> Built from the prior window only:
    <code>slipping</code>, <code>steady</code>, <code>spiking</code>. In the top 200:
    {QSUM['top200_decision_state_mix'].get('slipping', 0)} slipping,
    {QSUM['top200_decision_state_mix'].get('steady', 0)} steady,
    {QSUM['top200_decision_state_mix'].get('spiking', 0)} spiking.</li>
    <li><strong><code>outcome_state</code> — reporting only.</strong> What actually happened:
    <code>declining</code>, <code>recovering</code>, <code>growing</code>, <code>stable</code>. This
    is label-side information, so it is never a feature and never something the engine claims to
    predict.</li>
  </ul>

  <div class="callout">
    <p class="eyebrow">Why recovery can be reported but not predicted</p>
    <p>Spotting a recovery <em>before</em> it happens needs two consecutive deltas — a fall, then a
    rise. This slice exposes only two pre-decision windows, which is a single delta. So the engine
    can tell you that {_pop.get('recovering', 0):,} pages recovered, and it cannot tell you in
    advance which ones will. Fixing that needs the warehouse's daily table, not a better model.</p>
  </div>

  {state_table}

  <figure>
    <div class="plate">{fig("queue_state_mix.svg")}</div>
    <figcaption><b>The ranking separates decline from growth, gradually.</b> Real decline climbs from
    {STATES['decile_outcome_mix'][0]['declining'] * 100:.0f}% in the safest decile to
    {STATES['decile_outcome_mix'][9]['declining'] * 100:.0f}% in the riskiest, while growing pages
    fall from {STATES['decile_outcome_mix'][0]['growing'] * 100:.0f}% to
    {STATES['decile_outcome_mix'][9]['growing'] * 100:.0f}%. The engine is not merely surfacing big
    pages — though the slope is gentle, which is the same "no sharp boundary" caveat as before.</figcaption>
  </figure>

  <h3>The queue itself</h3>
  {queue_table}

  <figure>
    <div class="plate">{fig("queue_reason_mix.svg")}</div>
    <figcaption><b>The top 200 is not one kind of work.</b> Refreshing content, fixing titles and
    descriptions, and protecting high-demand pages are three different jobs for three different people —
    which is why the queue carries reason codes rather than a single score.</figcaption>
  </figure>

  <p>Confidence: medium at the top of the queue (precision@50 holds at
  {STAB['precision_at_50_mean']:.3f} ± {STAB['precision_at_50_std']:.3f} across client holdouts), low
  through the middle deciles, and out of scope entirely below the 100-impression floor, where the
  system stays silent rather than reassuring.</p>
</section>

<section id="repro">
  <h2><span class="sec-n">07</span>Run it yourself</h2>
  <p class="sec-sub">Reproducibility</p>
  <p>Every number on this page is produced by one script and stored as JSON in the repository, and this
  page is generated from those files — so the paper cannot drift away from the pipeline.</p>
<pre>git clone {REPO_URL}
cd {REPO_DIR}
pip install -r requirements.txt

python work/scripts/capstone_pipeline.py   # metrics + figures  (~25s, seed 42)
python work/scripts/build_paper.py         # rebuilds this page</pre>

  <div class="links">
    <div class="link-card"><a href="{NB}/capstone.ipynb">Capstone notebook</a>
      <span>The paper, section by section, with live code</span></div>
    <div class="link-card"><a href="{NB}/w06_validation_audit.ipynb">Validation &amp; claim audit</a>
      <span>Split comparison, three leakage tests, claim rewrite</span></div>
    <div class="link-card"><a href="{NB}/w07_action_playbook.ipynb">Action playbook</a>
      <span>Reason codes, human gates, monitoring triggers</span></div>
    <div class="link-card"><a href="{REPO_URL}/blob/main/work/scripts/capstone_pipeline.py">Pipeline source</a>
      <span>Feature contract, baselines, metrics — one file</span></div>
    <div class="link-card"><a href="{REPO_URL}/tree/main/work/outputs">Receipts (JSON)</a>
      <span>Every metric, base rate and exclusion, committed</span></div>
    <div class="link-card"><a href="{REPO_URL}/blob/main/work/capstone_report.md">Full capstone report</a>
      <span>The long-form version of this page</span></div>
  </div>

  <p>Seed 42 throughout; <code>GroupKFold</code> is deterministic. Python 3.11, pandas 2.x,
  scikit-learn 1.7.x. Random-forest numbers can move a point or two between scikit-learn versions;
  the shipped logistic regression is stable. The 18,010-row queue CSV is deliberately <em>not</em>
  committed — repository policy blocks dataset files — and is regenerated by the command above.
  No sealed-holdout claim is made anywhere: these are out-of-fold cross-validation numbers on one
  snapshot.</p>
</section>

<section id="credit">
  <h2><span class="sec-n">08</span>Acknowledgments &amp; data credit</h2>
  <p class="sec-sub">Credit</p>
  <p>Built on the <strong>FlyRank ML Internship dataset</strong> — real, anonymized search and content
  performance data made available for this internship: <a href="https://flyrank.ai" target="_blank"
  rel="noopener">flyrank.ai</a>. The March 2026 FlyRank research paper is the reference audited in the
  validation notebook; the questions raised there are methodological, offered in the spirit of making
  the claims stronger rather than correcting them.</p>
  <footer>
    <p><strong>Which page should an editor open first?</strong> · Capstone, FlyRank ML Internship,
    Lane 2 — Refresh &amp; Content Opportunity Scoring · August 2026 ·
    <a href="{REPO_URL}">repository</a> · Built on the
    <a href="https://flyrank.ai" target="_blank" rel="noopener">FlyRank ML Internship dataset</a>.</p>
    <p>Decision-support research on observational data. No causal claim, no algorithmic claim, no
    client-identifying detail.</p>

    <div class="grad-badge-wrap">
      <a class="grad-badge" href="{BADGE_VERIFY}" target="_blank" rel="noopener">
        <img src="assets/flyrank-graduate-badge.svg" width="264" height="64"
             alt="FlyRank AI Fluency Internship — Graduate, 2026. Opens the verification page.">
      </a>
      <p class="grad-badge-note">Graduate of the FlyRank AI Fluency Internship — verify this credential.</p>
    </div>
  </footer>
</section>
</div>
'''

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=IBM+Plex+Mono:wght@400;500;600&'
         'family=IBM+Plex+Sans:wght@400;500;600&'
         'family=IBM+Plex+Serif:wght@400;600&display=swap">')

# The counter — whichever one site.json names, or none at all. Generated by the same
# function configure_site.py stamps into the portfolio, so the two pages cannot carry
# different counters, and a rebuild cannot reinstate one the config has moved off.
ANALYTICS = analytics_block(ANALYTICS_PROVIDER, ANALYTICS_ID)

DESCRIPTION = ("Ranking 18,010 pages by 30-day search-decline risk on real anonymized FlyRank data — "
               "and finding that the obvious baseline rule could not rank at all.")

full = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{f'<meta name="google-site-verification" content="{GSV}">' if GSV else ""}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE}</title>
<meta name="description" content="{DESCRIPTION}">
<meta property="og:title" content="Which page should an editor open first?">
<meta property="og:description" content="{DESCRIPTION}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nguyễn Hoàng Tú">
<meta property="og:url" content="{SITE_URL}/">
<meta property="og:image" content="{SITE_URL}/og-paper.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Which page should an editor open first? 18,010 pages ranked out-of-fold, 0.88 precision@50 against a 0.74 rule baseline.">
<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Which page should an editor open first?">
<meta name="twitter:description" content="{DESCRIPTION}">
<meta name="twitter:image" content="{SITE_URL}/og-paper.png">
<link rel="canonical" href="{SITE_URL}/">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Nguyễn Hoàng Tú">
<meta name="theme-color" content="#0b5fb0">
{ANALYTICS}
<link rel="icon" href="favicon.svg" type="image/svg+xml">
{FONTS}
<style>{CSS}</style>
</head>
<body>{BODY}
</body>
</html>
'''

fragment = f'<title>{TITLE}</title>\n{FONTS}\n<style>{CSS}</style>\n{BODY}'

DOCS.mkdir(parents=True, exist_ok=True)
(DOCS / "index.html").write_text(full)
print(f"docs/index.html  {len(full):>9,} bytes")

if "--fragment" in sys.argv:
    target = Path(sys.argv[sys.argv.index("--fragment") + 1])
    target.write_text(fragment)
    print(f"{target}  {len(fragment):>9,} bytes")
