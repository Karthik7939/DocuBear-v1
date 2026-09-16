# DocAgent-v1 Human Review Checklist

**Purpose**: Mandatory 100% human review of all generated documents across all commits × conditions.
With only 4–5 commits × 2 repos × 3 conditions, the full corpus is small enough to review completely — partial spot-checks are not acceptable for a research paper at this sample size.

**How to use this checklist**:
1. For each row, open the generated document in the frontend at `http://localhost:3000/review`.
2. Read the documentation diff.
3. Rate it **Accept** (document is accurate and usable as-is) or **Reject** (requires manual editing).
4. Record your rating in the table below AND in `human_review_ratings.json` (format below).
5. After completing all rows, run:
   ```bash
   python backend/eval/paper_table_generator.py \
       --results backend/eval/outputs/benchmark_live_results.json \
       --kappa-input backend/eval/outputs/human_review_ratings.json \
       --accept-threshold 80.0
   ```

**Note on kappa**: The LLM Accuracy/Faithfulness score is binarized at threshold 80.0 (score ≥ 80 = Accept). This threshold is explicitly stated in all outputs. If every document is rated Accept by both you and the LLM (plausible at small n), kappa will be undefined — the script will warn you and report observed agreement (p_o) instead.

---

## Review Table

Fill in the **Human Rating** and **Notes** columns. All other columns are populated from `metrics.json` after real commits run.

| # | Repo | Commit SHA | Scope | Condition | Generated Doc | LLM Quality Score | LLM Faithfulness | Human Rating | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Mindstride | *(fill after commit)* | Small | Direct Diff | README.md | — | — | ☐ Accept / ☐ Reject | |
| 2 | Mindstride | *(fill after commit)* | Small | Standard RAG | README.md | — | — | ☐ Accept / ☐ Reject | |
| 3 | Mindstride | *(fill after commit)* | Small | DocAgent | README.md | — | — | ☐ Accept / ☐ Reject | |
| 4 | Mindstride | *(fill after commit)* | Small | DocAgent | ARCHITECTURE.md | — | — | ☐ Accept / ☐ Reject | |
| 5 | Mindstride | *(fill after commit)* | Medium | Direct Diff | README.md | — | — | ☐ Accept / ☐ Reject | |
| 6 | Mindstride | *(fill after commit)* | Medium | Standard RAG | README.md | — | — | ☐ Accept / ☐ Reject | |
| 7 | Mindstride | *(fill after commit)* | Medium | DocAgent | README.md | — | — | ☐ Accept / ☐ Reject | |
| 8 | Mindstride | *(fill after commit)* | Medium | DocAgent | ARCHITECTURE.md | — | — | ☐ Accept / ☐ Reject | |
| 9 | Mindstride | *(fill after commit)* | Large | Direct Diff | README.md | — | — | ☐ Accept / ☐ Reject | |
| 10 | Mindstride | *(fill after commit)* | Large | Standard RAG | README.md | — | — | ☐ Accept / ☐ Reject | |
| 11 | Mindstride | *(fill after commit)* | Large | DocAgent | README.md | — | — | ☐ Accept / ☐ Reject | |
| 12 | Mindstride | *(fill after commit)* | Large | DocAgent | ARCHITECTURE.md | — | — | ☐ Accept / ☐ Reject | |
| 13 | QPaper-Gen | *(fill after commit)* | Small | DocAgent | README.md | — | — | ☐ Accept / ☐ Reject | |
| 14 | QPaper-Gen | *(fill after commit)* | Medium | DocAgent | README.md | — | — | ☐ Accept / ☐ Reject | |
| 15 | QPaper-Gen | *(fill after commit)* | Medium | DocAgent | ARCHITECTURE.md | — | — | ☐ Accept / ☐ Reject | |
| 16 | QPaper-Gen | *(fill after commit)* | Large | DocAgent | README.md | — | — | ☐ Accept / ☐ Reject | |

---

## `human_review_ratings.json` Format

After filling in the table, create `backend/eval/outputs/human_review_ratings.json` with this format:

```json
{
  "mindstride_commit1_small_directdiff_README": {
    "human_accept": true,
    "llm_score": 54.3,
    "repo": "Mindstride",
    "commit_scope": "small",
    "condition": "Direct Diff (No RAG)",
    "document": "README.md"
  },
  "mindstride_commit1_small_docagent_ARCHITECTURE": {
    "human_accept": true,
    "llm_score": 91.7,
    "repo": "Mindstride",
    "commit_scope": "small",
    "condition": "DocAgent-v1 (Full Hybrid)",
    "document": "ARCHITECTURE.md"
  }
}
```

Key format: `{repo}_{commit_scope}_{condition_short}_{doctype}` (no spaces, all lowercase).

---

## Agreement Statistics (fill after running paper_table_generator.py)

- **Accept threshold used**: 80.0
- **Total documents reviewed**: ___
- **Observed agreement (p_o)**: ___
- **Expected agreement (p_e)**: ___
- **Cohen's κ**: ___
- **Interpretation**: κ > 0.6 = substantial agreement; κ > 0.8 = almost perfect agreement
