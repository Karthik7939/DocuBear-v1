"""
tests/test_eval.py
-------------------
Unit tests for backend evaluation scripts:
- eval/paper_table_generator.py
- eval/baseline_runner.py
- eval/retrieval_evaluator.py
"""

import json
from pathlib import Path
import pytest

from eval.baseline_runner import load_benchmark_config, run_dry_run_simulation, run_benchmark
from eval.paper_table_generator import (
    compute_quality_score,
    extract_component_scores,
    generate_sensitivity_analysis,
    rank_biserial_effect_size,
    run_wilcoxon_test,
    generate_wilcoxon_table,
    binarize_llm_score,
    compute_cohen_kappa,
    generate_latex_main_table,
    generate_latex_retrieval_table,
    generate_tables,
)
from eval.retrieval_evaluator import evaluate_retrieval


def test_baseline_runner_dry_run(tmp_path: Path):
    config_path = Path("backend/eval/benchmark_dataset.json")
    out_dir = tmp_path / "outputs"

    out_file = run_benchmark(config_path, out_dir, dry_run=True)
    assert out_file.is_file()
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload.get("is_dry_run") is True
    assert len(payload.get("results", [])) > 0


def test_paper_table_generator(tmp_path: Path):
    config_path = Path("backend/eval/benchmark_dataset.json")
    out_dir = tmp_path / "outputs"
    res_file = run_benchmark(config_path, out_dir, dry_run=True)

    gen_files = generate_tables(res_file, out_dir, accept_threshold=80.0)
    assert len(gen_files) == 5

    table1_text = (out_dir / "table1_main_results.tex").read_text(encoding="utf-8")
    assert "\\textbf{DocAgent-v1" in table1_text
    # Verify no invalid LaTeX syntax like '$\\mathbf{...$'
    assert "$\\mathbf{" not in table1_text

    table2_text = (out_dir / "table2_retrieval_eval.tex").read_text(encoding="utf-8")
    assert "$\\mathbf{" not in table2_text

    table3_text = (out_dir / "table3_weight_sensitivity.tex").read_text(encoding="utf-8")
    assert "Flat/equal" in table3_text
    assert "×" not in table3_text

    table4_text = (out_dir / "table4_wilcoxon_tests.tex").read_text(encoding="utf-8")
    assert "DocAgent vs Direct Diff" in table4_text


def test_cohen_kappa_computation():
    llm = [True, True, False, True]
    human = [True, True, False, False]
    res = compute_cohen_kappa(llm, human)
    assert res["p_observed"] == 0.75
    assert res["kappa"] is not None
