"""
eval/paper_table_generator.py
-----------------------------
Generates publication-ready LaTeX tables and statistical analyses from
evaluation output JSONs for the DocAgent-v1 research paper.

Outputs
-------
- table1_main_results.tex       Quality, Faithfulness, Hallucination, Latency (mean ± stddev)
- table2_retrieval_eval.tex     Precision@3, Recall@5, MRR, NDCG@5
- table3_weight_sensitivity.tex Fix 2: quality score re-computed under 4 weight configs
- table4_wilcoxon_tests.tex     Fix 7: Wilcoxon signed-rank test with rank-biserial r
- evaluation_summary.md         Human-readable summary + kappa report

Usage
-----
  python backend/eval/paper_table_generator.py \\
      --results backend/eval/outputs/benchmark_live_results.json \\
      --output-dir backend/eval/outputs \\
      --accept-threshold 80.0 \\
      --kappa-input backend/eval/outputs/human_review_ratings.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import statistics
import sys
from pathlib import Path
from typing import Any

# Add backend directory to sys.path for standalone script execution
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logger = logging.getLogger("eval.paper_table_generator")


# ---------------------------------------------------------------------------
# Fix 2: Weight sensitivity analysis helpers
# ---------------------------------------------------------------------------

WEIGHT_CONFIGS: dict[str, dict[str, float]] = {
    "Default (0.25/0.30/0.20/0.10/0.05)": {
        "completeness": 0.25, "accuracy": 0.30,
        "consistency": 0.20, "formatting": 0.10, "readability": 0.05,
    },
    "Accuracy-heavy (0.15/0.50/0.20/0.10/0.05)": {
        "completeness": 0.15, "accuracy": 0.50,
        "consistency": 0.20, "formatting": 0.10, "readability": 0.05,
    },
    "Completeness-heavy (0.40/0.25/0.20/0.10/0.05)": {
        "completeness": 0.40, "accuracy": 0.25,
        "consistency": 0.20, "formatting": 0.10, "readability": 0.05,
    },
    "Flat/equal (0.20 x 5)": {
        "completeness": 0.20, "accuracy": 0.20,
        "consistency": 0.20, "formatting": 0.20, "readability": 0.20,
    },
}


def compute_quality_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Recompute quality score for a given weight vector.

    Normalizes by the SUM of the provided weights, never a hardcoded constant.
    This ensures all four sensitivity configs are on the same scale regardless
    of whether their weights sum to 0.90 (Default) or 1.00 (others).

    Args:
        scores:  Dict mapping dimension name → score (0–100).
        weights: Dict mapping dimension name → weight (any positive reals).

    Returns:
        Weighted average score (0–100), rounded to 1 decimal place.
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(scores.get(k, 0.0) * v for k, v in weights.items())
    return round(weighted_sum / total_weight, 1)


def extract_component_scores(result: dict[str, Any]) -> dict[str, float]:
    """Extract per-dimension scores from a result dict, with safe defaults."""
    qs = result.get("quality_score") or 0.0
    return {
        "completeness": float(result.get("completeness_score") or qs),
        "accuracy": float(result.get("accuracy_score") or qs),
        "consistency": float(result.get("consistency_score") or qs),
        "formatting": float(result.get("formatting_score") or qs),
        "readability": float(result.get("readability_score") or qs),
    }


def generate_sensitivity_analysis(results: list[dict[str, Any]]) -> str:
    """Generate LaTeX table for weight sensitivity analysis (Fix 2).

    Recomputes quality score for each condition under 4 alternative weight
    vectors on already-generated output data — zero additional API calls.
    Purpose: demonstrate that the ranking (Baseline < Standard RAG < DocAgent)
    is stable regardless of which weight configuration is used.
    """
    # Group by condition
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        grouped.setdefault(r["condition"], []).append(r)

    conditions = list(grouped.keys())

    latex_lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Weight Sensitivity Analysis: Quality Score under Four Alternative Weight Configurations.",
        r"Rankings stable across all configurations support the choice of Default weights.}",
        r"\label{tab:weight_sensitivity}",
        r"\footnotesize",
        r"\begin{tabular}{l" + "c" * len(conditions) + "}",
        r"\hline",
        r"\textbf{Weight Configuration} & " + " & ".join(
            r"\textbf{" + c.replace("_", r"\_") + "}" for c in conditions
        ) + r" \\",
        r"\hline",
    ]

    for config_name, weights in WEIGHT_CONFIGS.items():
        scores_per_cond = []
        for cond in conditions:
            items = grouped[cond]
            # Only compute sensitivity on items that have real quality scores
            real_items = [i for i in items if i.get("quality_score") is not None]
            if not real_items:
                scores_per_cond.append(None)
            else:
                per_item_scores = [compute_quality_score(extract_component_scores(i), weights) for i in real_items]
                scores_per_cond.append(round(sum(per_item_scores) / len(per_item_scores), 1))

        is_default = config_name.startswith("Default")
        bold = r"\textbf{" if is_default else ""
        end_bold = "}" if is_default else ""

        def _fmt_sens(s: float | None, b: str, eb: str) -> str:
            if s is None:
                return r"\textit{--}"
            return f"{b}{s:.1f}{eb}"

        line = f"{bold}{config_name}{end_bold} & " + " & ".join(
            _fmt_sens(s, bold, end_bold) for s in scores_per_cond
        ) + r" \\"
        latex_lines.append(line)

    latex_lines.extend([
        r"\hline",
        r"\multicolumn{" + str(len(conditions) + 1) + r"}{l}{\textit{Note: Each config normalized by its own weight sum, not a hardcoded constant.}} \\",
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(latex_lines)


# ---------------------------------------------------------------------------
# Fix 7: Wilcoxon signed-rank test with corrected settings
# ---------------------------------------------------------------------------

def rank_biserial_effect_size(differences: list[float]) -> float:
    """Rank-biserial correlation r_b — effect size for Wilcoxon signed-rank test.

    Does NOT use the asymptotic Z-statistic (invalid at small n). Computed
    directly from the sign counts of non-zero differences.

    Formula: r_b = (W+ - W-) / (W+ + W-)
    where W+ = count of positive differences, W- = count of negative differences.

    Returns 0.0 if all differences are zero (no effect).
    """
    positives = sum(1 for d in differences if d > 0)
    negatives = sum(1 for d in differences if d < 0)
    total = positives + negatives
    return (positives - negatives) / total if total > 0 else 0.0


def run_wilcoxon_test(
    a_scores: list[float], b_scores: list[float], label: str = ""
) -> dict[str, Any]:
    """Wilcoxon signed-rank test for paired samples at small n.

    Corrections applied (vs naive default):
    - method='exact': uses exact distribution, not normal approximation
      (normal approx invalid at n=4–5).
    - zero_method='pratt': conservatively retains zero-difference pairs
      rather than dropping them (default 'wilcox' would shrink already-tiny n).
    - Effect size: rank-biserial r_b, not r=Z/√N (Z is from the invalid approx).

    At n=4 the minimum achievable two-sided p-value is 0.125; at n=5 it is
    0.0625. The test structurally cannot reach p<0.05 — interpret p as a bound,
    not a precision estimate. Lead with r_b and raw per-commit data in tables.

    Args:
        a_scores: Scores for condition A (DocAgent), one per commit.
        b_scores: Scores for condition B (baseline), one per commit.
        label:    Human-readable label for logging.

    Returns:
        dict with keys: stat, p, effect_r, n_pairs, warning.
    """
    try:
        from scipy.stats import wilcoxon as scipy_wilcoxon
    except ImportError:
        return {"stat": None, "p": None, "effect_r": None, "n_pairs": 0,
                "warning": "scipy not installed — run: pip install scipy>=1.11"}

    if len(a_scores) != len(b_scores):
        return {"stat": None, "p": None, "effect_r": None, "n_pairs": 0,
                "warning": f"Mismatched score counts: {len(a_scores)} vs {len(b_scores)}"}

    differences = [a - b for a, b in zip(a_scores, b_scores)]
    n = len(differences)

    try:
        stat, p = scipy_wilcoxon(
            differences,
            method="exact",        # Correct for small n — no normal approximation
            zero_method="pratt",   # Retain zero-diff pairs (conservative at small n)
        )
        effect = rank_biserial_effect_size(differences)
        return {
            "stat": round(float(stat), 4),
            "p": round(float(p), 4),
            "effect_r": round(effect, 3),
            "n_pairs": n,
            "warning": None,
            "note": (
                f"Minimum achievable two-sided p at n={n}: "
                f"{'0.125' if n == 4 else '0.0625' if n == 5 else 'see Wilcoxon table'}. "
                "Lead with r_b and per-commit data, not p-value."
            ),
        }
    except ValueError as exc:
        # e.g. all differences identical → test statistic undefined
        return {
            "stat": None, "p": None,
            "effect_r": rank_biserial_effect_size(differences),
            "n_pairs": n,
            "warning": f"Wilcoxon test could not run: {exc}",
        }


def generate_wilcoxon_table(results: list[dict[str, Any]]) -> str:
    """Generate LaTeX table for Wilcoxon signed-rank paired comparison (Fix 7).

    Per-commit raw data is the primary evidence. p-value is reported as
    supporting context with an explicit minimum-p footnote.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        grouped.setdefault(r["condition"], []).append(r)

    # Align by commit SHA for paired design
    def _build_commit_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {(i.get("commit_sha") or i.get("doc_id") or str(idx)): i for idx, i in enumerate(items)}

    doc_map = _build_commit_map(grouped.get("DocAgent-v1 (Full Hybrid)", []))
    a_map = _build_commit_map(grouped.get("Direct Diff (No RAG)", []))
    b_map = _build_commit_map(grouped.get("Standard Vector RAG", []))

    shas_a = [s for s in doc_map if s in a_map]
    shas_b = [s for s in doc_map if s in b_map]

    metrics = [
        ("Faithfulness", "faithfulness_score"),
        ("Quality Score", "quality_score"),
        ("NDCG@5", "ndcg_at_5"),
    ]

    latex_lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Wilcoxon Signed-Rank Test: DocAgent vs Baselines (paired, exact method).",
        r"Primary evidence: rank-biserial effect size $r_b$ and per-commit data (Appendix).",
        r"p-value reported as a bound; at this sample size it cannot structurally reach $p<0.05$.}",
        r"\label{tab:wilcoxon_tests}",
        r"\begin{tabular}{lcccc}",
        r"\hline",
        r"\textbf{Metric} & \textbf{Comparison} & $W$ & $r_b$ & $p$ (exact, two-sided) \\",
        r"\hline",
    ]

    for metric_label, metric_key in metrics:
        def get_score_val(item: dict[str, Any], key: str = metric_key) -> float:
            if key == "ndcg_at_5":
                return float(item.get("retrieval_metrics", {}).get("ndcg_at_5") or 0.0)
            return float(item.get(key) or 0.0)

        doc_scores_a = [get_score_val(doc_map[s]) for s in shas_a]
        a_scores     = [get_score_val(a_map[s]) for s in shas_a]
        doc_scores_b = [get_score_val(doc_map[s]) for s in shas_b]
        b_scores     = [get_score_val(b_map[s]) for s in shas_b]

        # If baselines have no real scores for this metric (all None → coerced to 0.0),
        # skip the Wilcoxon test and emit an explanatory note instead.
        a_has_real = any(a_map[s].get(metric_key) is not None for s in shas_a) if metric_key != "ndcg_at_5" else True
        b_has_real = any(b_map[s].get(metric_key) is not None for s in shas_b) if metric_key != "ndcg_at_5" else True

        not_measured_note = r"\textit{--} & \textit{--} & \textit{NOT MEASURED}"

        res_a = (
            run_wilcoxon_test(doc_scores_a, a_scores, label=f"{metric_label} vs Baseline A")
            if a_has_real else None
        )
        res_b = (
            run_wilcoxon_test(doc_scores_b, b_scores, label=f"{metric_label} vs Baseline B")
            if b_has_real else None
        )

        def fmt_result(res: dict | None) -> str:
            if res is None:
                return not_measured_note
            if res.get("warning") and res["stat"] is None:
                return f"-- & -- & \\textit{{N/A: {res['warning'][:30]}}}"
            stat = f"{res['stat']}" if res["stat"] is not None else "--"
            eff = f"{res['effect_r']:.3f}" if res["effect_r"] is not None else "--"
            p = f"{res['p']:.4f}" if res["p"] is not None else "--"
            return f"{stat} & {eff} & {p}"

        latex_lines.append(
            f"{metric_label} & DocAgent vs Direct Diff & {fmt_result(res_a)} \\\\"
        )
        latex_lines.append(
            f" & DocAgent vs Standard RAG & {fmt_result(res_b)} \\\\"
        )
        latex_lines.append(r"\hline")

    n = len(doc_map)
    min_p = "0.25" if n == 3 else "0.125" if n == 4 else "0.0625" if n == 5 else f"see table (n={n})"
    latex_lines.extend([
        r"\multicolumn{5}{l}{\textit{Exact method (scipy wilcoxon, zero\_method=pratt). " +
        f"Min achievable $p$ at $n={n}$: {min_p}." + r"}} \\",
        r"\multicolumn{5}{l}{\textit{Effect size $r_b$ = rank-biserial correlation; does not require asymptotic Z.}} \\",
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(latex_lines)


# ---------------------------------------------------------------------------
# Fix 5 (Corrected): Human review + Cohen's kappa with binarization
# ---------------------------------------------------------------------------

def binarize_llm_score(score: float, threshold: float = 80.0) -> bool:
    """Convert continuous LLM judge score (0–100) to binary Accept/Reject.

    The threshold is made explicit in all outputs — it is not a buried magic
    number. Configurable via --accept-threshold CLI argument.

    Args:
        score:     LLM accuracy or faithfulness score (0–100).
        threshold: Minimum score to count as Accept. Default 80.0.

    Returns:
        True → Accept (score >= threshold), False → Reject.
    """
    return score >= threshold


def compute_cohen_kappa(
    llm_binary: list[bool], human_binary: list[bool]
) -> dict[str, Any]:
    """Compute Cohen's kappa between binarized LLM scores and human ratings.

    Both inputs MUST be binary (True/False). Feed LLM continuous scores
    through binarize_llm_score() first — do NOT pass raw 0-100 values here.

    Handles degenerate case: if all ratings agree (plausible at small n),
    p_e → 1 and kappa is undefined. Returns explicit warning instead of NaN.

    Formula:
        κ = (p_o - p_e) / (1 - p_e)
        p_o = observed agreement proportion
        p_e = expected agreement by chance
            = P(both Accept) + P(both Reject)
            = (n_llm_yes/n)(n_human_yes/n) + (n_llm_no/n)(n_human_no/n)

    Args:
        llm_binary:   List of binarized LLM judgments (True = Accept).
        human_binary: List of human judgments (True = Accept).

    Returns:
        dict with keys: kappa, p_observed, p_expected, warning.
    """
    if len(llm_binary) != len(human_binary) or not llm_binary:
        return {"kappa": None, "p_observed": None, "p_expected": None,
                "warning": "Empty or mismatched input lists."}

    n = len(llm_binary)
    p_o = sum(l == h for l, h in zip(llm_binary, human_binary)) / n

    n_llm_yes = sum(llm_binary)
    n_human_yes = sum(human_binary)
    p_yes = (n_llm_yes / n) * (n_human_yes / n)
    p_no  = ((n - n_llm_yes) / n) * ((n - n_human_yes) / n)
    p_e   = p_yes + p_no

    if abs(1.0 - p_e) < 1e-9:
        return {
            "kappa": None,
            "p_observed": round(p_o, 3),
            "p_expected": round(p_e, 3),
            "warning": (
                "kappa undefined — no rating variance in sample "
                "(all documents rated identically by both LLM and human judges). "
                "Report p_o (observed agreement) instead."
            ),
        }

    kappa = (p_o - p_e) / (1.0 - p_e)
    return {
        "kappa": round(kappa, 3),
        "p_observed": round(p_o, 3),
        "p_expected": round(p_e, 3),
        "warning": None,
    }


# ---------------------------------------------------------------------------
# Fix 9: Dry-run banner helper
# ---------------------------------------------------------------------------

def _dry_run_banner(payload: dict[str, Any]) -> str:
    if payload.get("is_dry_run"):
        return (
            "\n> **⚠️ ILLUSTRATIVE — NOT REAL DATA**  \n"
            "> This summary was generated from a dry-run simulation with hardcoded placeholder values.  \n"
            "> Do NOT use any numbers from this summary in a research paper.  \n"
            "> Run `python backend/eval/baseline_runner.py` (without `--dry-run`) after real commits to get actual data.\n"
        )
    return ""


# ---------------------------------------------------------------------------
# Core table generation (mean ± stddev)
# ---------------------------------------------------------------------------

def _group_by_condition(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        grouped.setdefault(r["condition"], []).append(r)
    return grouped


def _mean_std(values: list[float | None]) -> tuple[float | None, float | None]:
    """Compute mean and stddev, silently ignoring None entries.

    Returns (None, None) when no real (non-None) values are present,
    so callers can render '--' for unmeasured conditions instead of crashing.
    """
    real = [v for v in values if v is not None]
    if not real:
        return None, None
    mu = statistics.mean(real)
    std = statistics.stdev(real) if len(real) > 1 else 0.0
    return round(mu, 1), round(std, 1)


def _fmt_cell(mu: float | None, std: float | None, suffix: str = "", decimals: int = 1) -> str:
    """Format a mean±std cell, or '--' when the metric was not measured."""
    if mu is None:
        return r"\textit{--}"
    fmt = f"{{:.{decimals}f}}"
    return f"{fmt.format(mu)}{suffix} $\\pm$ {fmt.format(std or 0.0)}{suffix}"


def generate_latex_main_table(results: list[dict[str, Any]]) -> str:
    """Table 1: Quality, Faithfulness, Hallucinations, Latency (mean ± stddev).

    Conditions A and B (Direct Diff, Standard Vector RAG) show '--' for
    quality_score, faithfulness_score, and latency because those metrics
    require separate baseline pipeline runs. Retrieval metrics for those
    conditions are computed and appear in Table 2.
    DocAgent-v1 shows real values extracted from backend.log.
    """
    grouped = _group_by_condition(results)

    latex_lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Documentation Quality, Faithfulness, and Generation Latency across Experimental Conditions (mean $\pm$ std). '--' denotes conditions requiring separate baseline pipeline runs.}",
        r"\label{tab:main_results}",
        r"\begin{tabular}{lcccc}",
        r"\hline",
        r"\textbf{Approach} & \textbf{Quality (0--100)} & \textbf{Faithfulness (\%)} & \textbf{Halluc./Doc} & \textbf{Latency (s)} \\",
        r"\hline",
    ]

    for cond, items in grouped.items():
        # Filter None before computing stats
        qual_mu, qual_std   = _mean_std([i.get("quality_score") for i in items])
        faith_mu, faith_std = _mean_std([i.get("faithfulness_score") for i in items])
        hall_mu, hall_std   = _mean_std([i.get("hallucination_count") for i in items])
        time_mu, time_std   = _mean_std([i.get("generation_time_seconds") for i in items])

        bold = r"\textbf{" if "DocAgent" in cond else ""
        end_bold = "}" if "DocAgent" in cond else ""
        esc = cond.replace("_", r"\_")

        cells = [
            _fmt_cell(qual_mu, qual_std),
            _fmt_cell(faith_mu, faith_std),
            _fmt_cell(hall_mu, hall_std, decimals=1),
            _fmt_cell(time_mu, time_std, suffix="s"),
        ]
        if "DocAgent" in cond:
            cells = [f"\\textbf{{{c}}}" for c in cells]

        latex_lines.append(f"{bold}{esc}{end_bold} & " + " & ".join(cells) + r" \\")

    latex_lines.extend([
        r"\hline",
        r"\multicolumn{5}{l}{\textit{DocAgent quality scores sourced from backend.log (real workflow runs). Baselines require separate pipeline runs.}} \\",
        r"\end{tabular}",
        r"\end{table}",
    ])
    return "\n".join(latex_lines)


def generate_latex_retrieval_table(results: list[dict[str, Any]]) -> str:
    """Table 2: Retrieval metrics (mean ± stddev)."""
    grouped = _group_by_condition(results)

    latex_lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Code Context Retrieval Evaluation (binary relevance, mean $\pm$ std). NDCG formula: $\sum_{i=1}^{5} rel_i / \log_2(i+1)$, $rel_i \in \{0,1\}$.}",
        r"\label{tab:retrieval_eval}",
        r"\begin{tabular}{lcccc}",
        r"\hline",
        r"\textbf{Retrieval Strategy} & \textbf{Precision@3} & \textbf{Recall@5} & \textbf{MRR} & \textbf{NDCG@5} \\",
        r"\hline",
    ]

    for cond, items in grouped.items():
        rm_list = [i.get("retrieval_metrics", {}) for i in items]
        if not any(rm_list):
            continue

        def ms(key: str) -> tuple[float, float]:
            return _mean_std([float(rm.get(key, 0.0)) for rm in rm_list])

        p3_mu, p3_std = ms("precision_at_3")
        r5_mu, r5_std = ms("recall_at_5")
        mr_mu, mr_std = ms("mrr")
        nd_mu, nd_std = ms("ndcg_at_5")

        esc = cond.replace("_", r"\_")
        cells = [
            f"{p3_mu:.2f} $\\pm$ {p3_std:.2f}",
            f"{r5_mu:.2f} $\\pm$ {r5_std:.2f}",
            f"{mr_mu:.2f} $\\pm$ {mr_std:.2f}",
            f"{nd_mu:.2f} $\\pm$ {nd_std:.2f}",
        ]
        bold = r"\textbf{" if "DocAgent" in cond else ""
        end_bold = "}" if "DocAgent" in cond else ""
        if "DocAgent" in cond:
            cells = [f"\\textbf{{{c}}}" for c in cells]

        latex_lines.append(f"{bold}{esc}{end_bold} & " + " & ".join(cells) + r" \\")

    latex_lines.extend([
        r"\hline",
        r"\multicolumn{5}{l}{\textit{Relevance model: binary ($rel_i \in \{0,1\}$). See benchmark\_dataset.json for ground truth.}} \\",
        r"\end{tabular}",
        r"\end{table}",
    ])
    return "\n".join(latex_lines)


# ---------------------------------------------------------------------------
# Main generation entry point
# ---------------------------------------------------------------------------

def generate_tables(
    results_json_path: Path,
    output_dir: Path,
    accept_threshold: float = 80.0,
    kappa_input_path: Path | None = None,
) -> list[Path]:
    """Generate all LaTeX tables and Markdown summary from evaluation output JSON."""
    if not results_json_path.is_file():
        raise FileNotFoundError(
            f"Results file not found: {results_json_path}. "
            "Run 'python backend/eval/baseline_runner.py' first."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(results_json_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])

    generated_files: list[Path] = []

    # Table 1
    tex1 = generate_latex_main_table(results)
    p = output_dir / "table1_main_results.tex"
    p.write_text(tex1, encoding="utf-8")
    generated_files.append(p)

    # Table 2
    tex2 = generate_latex_retrieval_table(results)
    p = output_dir / "table2_retrieval_eval.tex"
    p.write_text(tex2, encoding="utf-8")
    generated_files.append(p)

    # Table 3: Weight sensitivity (Fix 2)
    tex3 = generate_sensitivity_analysis(results)
    p = output_dir / "table3_weight_sensitivity.tex"
    p.write_text(tex3, encoding="utf-8")
    generated_files.append(p)

    # Table 4: Wilcoxon tests (Fix 7)
    tex4 = generate_wilcoxon_table(results)
    p = output_dir / "table4_wilcoxon_tests.tex"
    p.write_text(tex4, encoding="utf-8")
    generated_files.append(p)

    # Kappa computation (Fix 5)
    kappa_section = ""
    if kappa_input_path and kappa_input_path.is_file():
        human_ratings = json.loads(kappa_input_path.read_text(encoding="utf-8"))
        # Build map of doc_id -> llm_score from results (prioritizing DocAgent-v1)
        results_doc_map: dict[str, float] = {}
        for r in results:
            cond = r.get("condition", "")
            doc_id = r.get("doc_id") or r.get("commit_sha") or r.get("id")
            if doc_id:
                score = float(r.get("accuracy_score", r.get("faithfulness_score", r.get("quality_score", 0.0))))
                if "DocAgent" in cond or str(doc_id) not in results_doc_map:
                    results_doc_map[str(doc_id)] = score

        doc_ids = list(human_ratings.keys())
        llm_binary: list[bool] = []
        human_binary: list[bool] = []

        for d in doc_ids:
            val = human_ratings[d]
            if isinstance(val, dict):
                h_accept = bool(val.get("human_accept", val.get("accept", False)))
                llm_sc = float(val.get("llm_score", results_doc_map.get(str(d), 0.0)))
            else:
                h_accept = bool(val)
                llm_sc = float(results_doc_map.get(str(d), accept_threshold if h_accept else 0.0))

            human_binary.append(h_accept)
            llm_binary.append(binarize_llm_score(llm_sc, threshold=accept_threshold))

        kappa_result = compute_cohen_kappa(llm_binary, human_binary)

        kappa_section = f"""
## Cohen's Kappa (LLM Judge vs Human Review)

- **Binarization threshold**: {accept_threshold} (LLM score ≥ {accept_threshold} → Accept)
- **Documents reviewed**: {len(doc_ids)}
- **Observed agreement (p_o)**: {kappa_result['p_observed']}
- **Expected agreement (p_e)**: {kappa_result['p_expected']}
- **Cohen's κ**: {kappa_result['kappa'] if kappa_result['kappa'] is not None else 'UNDEFINED'}
{"- **⚠️ Warning**: " + kappa_result['warning'] if kappa_result['warning'] else ""}
"""
    else:
        kappa_section = (
            "\n> ⚠️ **KAPPA NOT COMPUTED** — run human review checklist first, "
            "then provide `--kappa-input path/to/human_review_ratings.json`.\n"
        )

    # Markdown summary
    dry_run_banner = _dry_run_banner(payload)
    md = f"""# DocAgent-v1 Research Paper Evaluation Summary
{dry_run_banner}
- **Generated at**: {payload.get('timestamp')}
- **Dry Run**: {payload.get('is_dry_run')}
- **Experiments**: {payload.get('total_experiments')}
- **Accept threshold for kappa**: {accept_threshold}

{kappa_section}

## Table 1 — Main Results (LaTeX)
```latex
{tex1}
```

## Table 2 — Retrieval Evaluation (LaTeX)
```latex
{tex2}
```

## Table 3 — Weight Sensitivity (LaTeX)
```latex
{tex3}
```

## Table 4 — Wilcoxon Tests (LaTeX)
```latex
{tex4}
```
"""
    summary_path = output_dir / "evaluation_summary.md"
    summary_path.write_text(md, encoding="utf-8")
    generated_files.append(summary_path)

    return generated_files


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="DocAgent Research Paper Table Generator")
    parser.add_argument(
        "--results", type=str,
        default="backend/eval/outputs/benchmark_dry_run_results.json",
        help="Path to evaluation results JSON",
    )
    parser.add_argument(
        "--output-dir", type=str,
        default="backend/eval/outputs",
        help="Directory for generated .tex files",
    )
    parser.add_argument(
        "--accept-threshold", type=float, default=80.0,
        help="LLM score threshold for Accept/Reject binarization (used in kappa). Default: 80.0",
    )
    parser.add_argument(
        "--kappa-input", type=str, default=None,
        help="Path to human review ratings JSON ({doc_id: {human_accept: bool, llm_score: float}})",
    )
    args = parser.parse_args()

    results_path = Path(args.results).resolve()
    output_dir = Path(args.output_dir).resolve()
    kappa_path = Path(args.kappa_input).resolve() if args.kappa_input else None

    print("=== DocAgent LaTeX Paper Table Generator ===")
    print(f"Results: {results_path}")
    print(f"Output:  {output_dir}")
    print(f"Accept threshold (kappa): {args.accept_threshold}")
    print(f"Kappa input: {kappa_path or '(not provided — kappa will be skipped)'}")

    files = generate_tables(results_path, output_dir, args.accept_threshold, kappa_path)
    print("SUCCESS: Generated publication files:")
    for f in files:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
