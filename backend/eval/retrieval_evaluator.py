"""
eval/retrieval_evaluator.py
----------------------------
Evaluation metrics calculator for Retrieval-Augmented Generation (RAG).

Calculates IR (Information Retrieval) metrics for evaluating code retrieval:
- Precision@K
- Recall@K
- Mean Reciprocal Rank (MRR)
- Normalized Discounted Cumulative Gain (NDCG@K)

Relevance model
---------------
All metrics use **binary** relevance: rel_i ∈ {0, 1}.
A retrieved file is relevant (rel_i = 1) if it appears in ground_truth_files,
and irrelevant (rel_i = 0) otherwise. Partial credit is not used.

NDCG formula (standard 1-based formulation used throughout)
------------------------------------------------------------
    DCG@K  = Σ_{i=1}^{K}  rel_i / log2(i + 1)
    IDCG@K = Σ_{i=1}^{min(|R|, K)}  1 / log2(i + 1)   where |R| = |ground_truth|
    NDCG@K = DCG@K / IDCG@K   (0 if IDCG@K = 0)

The 1-based index (i = 1..K, divisor log2(i+1)) is the form cited in standard
IR literature (Manning et al., 2008). An equivalent 0-based form with log2(i+2)
also produces correct values but is non-standard for paper citation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


def _is_relevant(item: str, ground_truth: Sequence[str]) -> bool:
    """Binary relevance check: True if item matches any ground-truth file path.

    Uses substring containment in both directions to handle partial paths
    (e.g. 'backend/app/auth.py' matches ground-truth 'auth.py' and vice versa).
    """
    return any(gt in item or item in gt for gt in ground_truth)


@dataclass
class RetrievalEvalMetrics:
    """IR evaluation metrics for a single query or retrieval run.

    All scores use binary relevance (rel_i ∈ {0, 1}).
    See module docstring for full NDCG formula and relevance definition.
    """

    precision_at_1: float = 0.0
    precision_at_3: float = 0.0
    precision_at_5: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    mrr: float = 0.0
    ndcg_at_5: float = 0.0
    retrieved_count: int = 0
    relevant_count: int = 0
    retrieved_relevant_count: int = 0
    # Explicit relevance mode — always "binary" for now; stored in output JSON
    # so benchmark results self-document their relevance definition.
    relevance_mode: str = "binary"


def calculate_precision_at_k(retrieved: Sequence[str], ground_truth: Sequence[str], k: int) -> float:
    """Calculate Precision@K: fraction of top-K retrieved items that are relevant.

    Formula: |{top-K retrieved} ∩ {ground truth}| / K
    """
    if not retrieved or k <= 0:
        return 0.0
    top_k = retrieved[:k]
    relevant_found = sum(1 for item in top_k if _is_relevant(item, ground_truth))
    return relevant_found / min(k, len(top_k))


def calculate_recall_at_k(retrieved: Sequence[str], ground_truth: Sequence[str], k: int) -> float:
    """Calculate Recall@K: fraction of all relevant items retrieved in top-K.

    Formula: |{top-K retrieved} ∩ {ground truth}| / |ground truth|
    """
    if not ground_truth or k <= 0:
        return 0.0
    top_k = retrieved[:k]
    relevant_found = sum(1 for gt in ground_truth if any(gt in item or item in gt for item in top_k))
    return relevant_found / len(ground_truth)


def calculate_mrr(retrieved: Sequence[str], ground_truth: Sequence[str]) -> float:
    """Calculate Mean Reciprocal Rank (MRR): 1 / rank of first relevant item.

    Formula: 1 / rank_first_relevant   (0 if no relevant item found)
    """
    for rank, item in enumerate(retrieved, start=1):
        if _is_relevant(item, ground_truth):
            return 1.0 / rank
    return 0.0


def calculate_ndcg_at_k(retrieved: Sequence[str], ground_truth: Sequence[str], k: int) -> float:
    """Calculate NDCG@K using standard 1-based binary relevance.

    Formula (1-based index, i = 1..K):
        DCG@K  = Σ_{i=1}^{K}   rel_i / log2(i + 1)
        IDCG@K = Σ_{i=1}^{min(|R|,K)}  1 / log2(i + 1)
        NDCG@K = DCG@K / IDCG@K   (0.0 if IDCG@K = 0)

    rel_i ∈ {0, 1} (binary). |R| = number of ground-truth relevant files.

    The 1-based formulation (divisor log2(i+1) where i starts at 1) is the
    standard form cited in IR literature — use this form when citing in papers.
    """
    if not retrieved or not ground_truth or k <= 0:
        return 0.0
    top_k = retrieved[:k]

    # DCG@K — i is 1-based
    dcg = 0.0
    for i, item in enumerate(top_k, start=1):
        rel = 1.0 if _is_relevant(item, ground_truth) else 0.0
        dcg += rel / math.log2(i + 1)

    # IDCG@K — perfect ranking: all ground-truth items at top positions
    num_relevant = min(len(ground_truth), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, num_relevant + 1))

    return dcg / idcg if idcg > 0 else 0.0


def evaluate_retrieval(retrieved_files: list[str], ground_truth_files: list[str]) -> RetrievalEvalMetrics:
    """Compute the full retrieval evaluation metric suite for one query result.

    Args:
        retrieved_files:    Ordered list of file paths returned by the retrieval system.
                            Order matters for rank-sensitive metrics (MRR, NDCG).
        ground_truth_files: Unordered list of file paths that are truly relevant
                            for this commit (binary relevance: present = relevant).

    Returns:
        RetrievalEvalMetrics with all metrics set and relevance_mode = "binary".
    """
    if not retrieved_files or not ground_truth_files:
        return RetrievalEvalMetrics(
            relevant_count=len(ground_truth_files),
            relevance_mode="binary",
        )

    p1 = calculate_precision_at_k(retrieved_files, ground_truth_files, 1)
    p3 = calculate_precision_at_k(retrieved_files, ground_truth_files, 3)
    p5 = calculate_precision_at_k(retrieved_files, ground_truth_files, 5)
    r3 = calculate_recall_at_k(retrieved_files, ground_truth_files, 3)
    r5 = calculate_recall_at_k(retrieved_files, ground_truth_files, 5)
    mrr = calculate_mrr(retrieved_files, ground_truth_files)
    ndcg5 = calculate_ndcg_at_k(retrieved_files, ground_truth_files, 5)

    rel_found = sum(1 for item in retrieved_files if _is_relevant(item, ground_truth_files))

    return RetrievalEvalMetrics(
        precision_at_1=round(p1, 4),
        precision_at_3=round(p3, 4),
        precision_at_5=round(p5, 4),
        recall_at_3=round(r3, 4),
        recall_at_5=round(r5, 4),
        mrr=round(mrr, 4),
        ndcg_at_5=round(ndcg5, 4),
        retrieved_count=len(retrieved_files),
        relevant_count=len(ground_truth_files),
        retrieved_relevant_count=rel_found,
        relevance_mode="binary",
    )
