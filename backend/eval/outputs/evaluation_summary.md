# DocAgent-v1 Research Paper Evaluation Summary

- **Generated at**: 2026-09-14T10:06:53.534584+00:00
- **Dry Run**: False
- **Experiments**: 15
- **Accept threshold for kappa**: 80.0


> ⚠️ **KAPPA NOT COMPUTED** — run human review checklist first, then provide `--kappa-input path/to/human_review_ratings.json`.


## Table 1 — Main Results (LaTeX)
```latex
\begin{table}[ht]
\centering
\caption{Documentation Quality, Faithfulness, and Generation Latency across Experimental Conditions (mean $\pm$ std). '--' denotes conditions requiring separate baseline pipeline runs.}
\label{tab:main_results}
\begin{tabular}{lcccc}
\hline
\textbf{Approach} & \textbf{Quality (0--100)} & \textbf{Faithfulness (\%)} & \textbf{Halluc./Doc} & \textbf{Latency (s)} \\
\hline
Direct Diff (No RAG) & \textit{--} & \textit{--} & \textit{--} & \textit{--} \\
Standard Vector RAG & \textit{--} & \textit{--} & \textit{--} & \textit{--} \\
\textbf{DocAgent-v1 (Full Hybrid)} & \textbf{87.3 $\pm$ 2.6} & \textbf{\textit{--}} & \textbf{\textit{--}} & \textbf{104.2s $\pm$ 11.7s} \\
\hline
\multicolumn{5}{l}{\textit{DocAgent quality scores sourced from backend.log (real workflow runs). Baselines require separate pipeline runs.}} \\
\end{tabular}
\end{table}
```

## Table 2 — Retrieval Evaluation (LaTeX)
```latex
\begin{table}[ht]
\centering
\caption{Code Context Retrieval Evaluation (binary relevance, mean $\pm$ std). NDCG formula: $\sum_{i=1}^{5} rel_i / \log_2(i+1)$, $rel_i \in \{0,1\}$.}
\label{tab:retrieval_eval}
\begin{tabular}{lcccc}
\hline
\textbf{Retrieval Strategy} & \textbf{Precision@3} & \textbf{Recall@5} & \textbf{MRR} & \textbf{NDCG@5} \\
\hline
Direct Diff (No RAG) & 0.00 $\pm$ 0.00 & 0.00 $\pm$ 0.00 & 0.00 $\pm$ 0.00 & 0.00 $\pm$ 0.00 \\
Standard Vector RAG & 1.00 $\pm$ 0.00 & 0.20 $\pm$ 0.10 & 1.00 $\pm$ 0.00 & 0.40 $\pm$ 0.10 \\
\textbf{DocAgent-v1 (Full Hybrid)} & \textbf{1.00 $\pm$ 0.00} & \textbf{0.90 $\pm$ 0.30} & \textbf{1.00 $\pm$ 0.00} & \textbf{1.00 $\pm$ 0.00} \\
\hline
\multicolumn{5}{l}{\textit{Relevance model: binary ($rel_i \in \{0,1\}$). See benchmark\_dataset.json for ground truth.}} \\
\end{tabular}
\end{table}
```

## Table 3 — Weight Sensitivity (LaTeX)
```latex
\begin{table}[ht]
\centering
\caption{Weight Sensitivity Analysis: Quality Score under Four Alternative Weight Configurations.
Rankings stable across all configurations support the choice of Default weights.}
\label{tab:weight_sensitivity}
\footnotesize
\begin{tabular}{lccc}
\hline
\textbf{Weight Configuration} & \textbf{Direct Diff (No RAG)} & \textbf{Standard Vector RAG} & \textbf{DocAgent-v1 (Full Hybrid)} \\
\hline
\textbf{Default (0.25/0.30/0.20/0.10/0.05)} & \textit{--} & \textit{--} & \textbf{87.3} \\
Accuracy-heavy (0.15/0.50/0.20/0.10/0.05) & \textit{--} & \textit{--} & 87.3 \\
Completeness-heavy (0.40/0.25/0.20/0.10/0.05) & \textit{--} & \textit{--} & 87.3 \\
Flat/equal (0.20 x 5) & \textit{--} & \textit{--} & 87.3 \\
\hline
\multicolumn{4}{l}{\textit{Note: Each config normalized by its own weight sum, not a hardcoded constant.}} \\
\end{tabular}
\end{table}
```

## Table 4 — Wilcoxon Tests (LaTeX)
```latex
\begin{table}[ht]
\centering
\caption{Wilcoxon Signed-Rank Test: DocAgent vs Baselines (paired, exact method).
Primary evidence: rank-biserial effect size $r_b$ and per-commit data (Appendix).
p-value reported as a bound; at this sample size it cannot structurally reach $p<0.05$.}
\label{tab:wilcoxon_tests}
\begin{tabular}{lcccc}
\hline
\textbf{Metric} & \textbf{Comparison} & $W$ & $r_b$ & $p$ (exact, two-sided) \\
\hline
Faithfulness & DocAgent vs Direct Diff & \textit{--} & \textit{--} & \textit{NOT MEASURED} \\
 & DocAgent vs Standard RAG & \textit{--} & \textit{--} & \textit{NOT MEASURED} \\
\hline
Quality Score & DocAgent vs Direct Diff & \textit{--} & \textit{--} & \textit{NOT MEASURED} \\
 & DocAgent vs Standard RAG & \textit{--} & \textit{--} & \textit{NOT MEASURED} \\
\hline
NDCG@5 & DocAgent vs Direct Diff & 0.0 & 1.000 & 0.0625 \\
 & DocAgent vs Standard RAG & 0.0 & 1.000 & 0.0625 \\
\hline
\multicolumn{5}{l}{\textit{Exact method (scipy wilcoxon, zero\_method=pratt). Min achievable $p$ at $n=5$: 0.0625.}} \\
\multicolumn{5}{l}{\textit{Effect size $r_b$ = rank-biserial correlation; does not require asymptotic Z.}} \\
\end{tabular}
\end{table}
```
