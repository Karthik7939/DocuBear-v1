"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Repo,
  RequirementsAnalysisResult,
  RequirementsSummary,
  RequirementItem,
} from "@/types";
import { AnimatedContainer, AnimatedItem } from "@/components/AnimatedItem";
import RadialMeter from "@/components/analytics/RadialMeter";

const REPO_STORAGE_KEY = "docubear_requirements_repo";

type ViewMode = "split" | "list" | "table";
type TabFilter = "all" | "passed" | "pending" | "partial" | "functional" | "non_functional";

function RequirementsContent() {
  const searchParams = useSearchParams();
  const repoParam = searchParams.get("repo");

  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [allSummaries, setAllSummaries] = useState<RequirementsSummary[]>([]);
  const [analysis, setAnalysis] = useState<RequirementsAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadStep, setUploadStep] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // View Mode: split (side-by-side passed vs pending), list (tabbed cards), table (matrix)
  const [viewMode, setViewMode] = useState<ViewMode>("split");

  // Filter tab for list/table views
  const [activeTab, setActiveTab] = useState<TabFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [isDragging, setIsDragging] = useState(false);

  // Fetch all saved summaries across projects in memory
  const fetchAllSummaries = useCallback(async () => {
    try {
      const res = await fetch("/api/requirements", { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setAllSummaries(data || []);
      }
    } catch {
      // ignore
    }
  }, []);

  // Fetch all repos on mount
  useEffect(() => {
    fetchAllSummaries();
    fetch("/api/repos")
      .then((res) => res.json())
      .then((data: Repo[]) => {
        setRepos(data);
        if (repoParam && data.some((r) => r.fullName === repoParam)) {
          setSelectedRepo(repoParam);
        } else {
          try {
            const saved = window.localStorage.getItem(REPO_STORAGE_KEY);
            if (saved && data.some((r) => r.fullName === saved)) {
              setSelectedRepo(saved);
            } else if (data.length > 0) {
              setSelectedRepo(data[0].fullName);
            }
          } catch {
            if (data.length > 0) setSelectedRepo(data[0].fullName);
          }
        }
      })
      .catch(() => setRepos([]));
  }, [repoParam, fetchAllSummaries]);

  // Load requirements for selectedRepo
  const fetchRequirements = useCallback(async (repoName: string) => {
    if (!repoName) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/requirements/${encodeURIComponent(repoName)}`, {
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        setAnalysis(data);
      } else {
        setAnalysis(null);
      }
    } catch {
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedRepo) {
      try {
        window.localStorage.setItem(REPO_STORAGE_KEY, selectedRepo);
      } catch {
        // ignore
      }
      fetchRequirements(selectedRepo);
    }
  }, [selectedRepo, fetchRequirements]);

  // Handle PDF upload
  async function handleFileUpload(file: File) {
    if (!selectedRepo) {
      setError("Please select a repository first.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please upload a valid PDF document (.pdf).");
      return;
    }

    setUploading(true);
    setError(null);
    setSuccessMsg(null);
    setUploadStep("Reading PDF & extracting all requirements with Groq AI...");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("repository", selectedRepo);

    try {
      setTimeout(() => {
        setUploadStep("Cross-referencing requirements with codebase RAG index & symbol tree...");
      }, 2500);

      const res = await fetch("/api/requirements/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.error || "Failed to analyze requirements PDF.");
      }

      setAnalysis(data);
      fetchAllSummaries();
      const passedCount = (data.functionalCount?.completed || 0) + (data.nonFunctionalCount?.completed || 0);
      setSuccessMsg(
        `Successfully analyzed "${file.name}"! Extracted all ${data.items?.length || 0} requirements (${passedCount} passed).`
      );
      setTimeout(() => setSuccessMsg(null), 6000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error uploading requirements document.");
    } finally {
      setUploading(false);
      setUploadStep("");
    }
  }

  // Handle re-verify against latest REQUIREMENTS.md
  async function handleReanalyze() {
    if (!selectedRepo || !analysis) return;
    setUploading(true);
    setError(null);
    setUploadStep("Re-evaluating requirements against latest REQUIREMENTS.md specification...");

    try {
      const res = await fetch(`/api/requirements/${encodeURIComponent(selectedRepo)}`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.error || "Re-verification failed.");
      }
      setAnalysis(data);
      fetchAllSummaries();
      setSuccessMsg("Requirements re-verified against latest REQUIREMENTS.md specification!");
      setTimeout(() => setSuccessMsg(null), 5000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Re-verification failed.");
    } finally {
      setUploading(false);
      setUploadStep("");
    }
  }

  // Categories list
  const categories = useMemo(() => {
    if (!analysis?.items) return [];
    const set = new Set<string>();
    analysis.items.forEach((item) => {
      if (item.category) set.add(item.category);
    });
    return Array.from(set);
  }, [analysis]);

  // Counts
  const totalPassed = useMemo(() => {
    if (!analysis?.items) return 0;
    return analysis.items.filter((i) => i.status === "completed").length;
  }, [analysis]);

  const totalPartial = useMemo(() => {
    if (!analysis?.items) return 0;
    return analysis.items.filter((i) => i.status === "partial").length;
  }, [analysis]);

  const totalMissing = useMemo(() => {
    if (!analysis?.items) return 0;
    return analysis.items.filter((i) => i.status === "missing").length;
  }, [analysis]);

  const totalPending = totalPartial + totalMissing;

  const totalReqs = useMemo(() => {
    if (!analysis?.items) return 0;
    return analysis.items.length;
  }, [analysis]);

  // Filter requirement helper
  const filterRequirement = useCallback(
    (item: RequirementItem) => {
      if (selectedCategory !== "all" && item.category !== selectedCategory) return false;

      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesTitle = item.title.toLowerCase().includes(query);
        const matchesDesc = item.description.toLowerCase().includes(query);
        const matchesId = item.id.toLowerCase().includes(query);
        const matchesCat = item.category.toLowerCase().includes(query);
        const matchesFiles = item.evidence_files.some((f) => f.toLowerCase().includes(query));
        const matchesRemediation = item.remediation?.toLowerCase().includes(query);
        return matchesTitle || matchesDesc || matchesId || matchesCat || matchesFiles || matchesRemediation;
      }

      return true;
    },
    [selectedCategory, searchQuery]
  );

  // Items for Side-by-Side Split View
  const passedItems = useMemo(() => {
    if (!analysis?.items) return [];
    return analysis.items.filter((i) => i.status === "completed" && filterRequirement(i));
  }, [analysis, filterRequirement]);

  const pendingItems = useMemo(() => {
    if (!analysis?.items) return [];
    return analysis.items.filter((i) => (i.status === "missing" || i.status === "partial") && filterRequirement(i));
  }, [analysis, filterRequirement]);

  // Items for Tabbed List View
  const filteredItems = useMemo(() => {
    if (!analysis?.items) return [];
    return analysis.items.filter((item) => {
      if (activeTab === "passed" && item.status !== "completed") return false;
      if (activeTab === "pending" && item.status === "completed") return false;
      if (activeTab === "partial" && item.status !== "partial") return false;
      if (activeTab === "functional" && item.type !== "functional") return false;
      if (activeTab === "non_functional" && item.type !== "non_functional") return false;

      return filterRequirement(item);
    });
  }, [analysis, activeTab, filterRequirement]);

  // Status helper
  function scoreStatus(score: number): "good" | "warning" | "danger" {
    if (score >= 80) return "good";
    if (score >= 50) return "warning";
    return "danger";
  }

  // Export Passed Checklist
  function handleExportPassed() {
    if (!analysis) return;
    const passedList = analysis.items.filter((i) => i.status === "completed");
    const lines = [
      `# Passed Requirements Verification Report`,
      `**Repository:** ${analysis.repository}`,
      `**Specification Document:** ${analysis.fileName}`,
      `**Verified At:** ${new Date(analysis.analyzedAt).toLocaleString()}`,
      `**Total Passed:** ${passedList.length} / ${analysis.items.length} (${analysis.overallScore}% score)`,
      ``,
      `## Passed Requirements Checklist`,
      ``,
      ...passedList.map((item) =>
        [
          `### ✅ ${item.id}: ${item.title} (${item.category})`,
          `- **Type:** ${item.type === "functional" ? "Functional Requirement" : "Non-Functional Requirement"}`,
          `- **Confidence:** ${(item.confidence * 100).toFixed(0)}%`,
          `- **Description:** ${item.description}`,
          `- **Verified Evidence Files:** ${item.evidence_files.join(", ") || "Codebase symbols"}`,
          item.evidence_snippet ? `- **Code Evidence Snippet:**\n\`\`\`python\n${item.evidence_snippet}\n\`\`\`` : "",
          ``,
        ]
          .filter(Boolean)
          .join("\n")
      ),
    ];

    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Passed_Requirements_${analysis.repository.replace("/", "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // Export Pending & Gaps Checklist
  function handleExportPending() {
    if (!analysis) return;
    const pendingList = analysis.items.filter((i) => i.status !== "completed");
    const lines = [
      `# Pending & Gap Remediation Action Plan`,
      `**Repository:** ${analysis.repository}`,
      `**Specification Document:** ${analysis.fileName}`,
      `**Generated:** ${new Date(analysis.analyzedAt).toLocaleString()}`,
      `**Pending Items:** ${pendingList.length} / ${analysis.items.length} (${analysis.overallScore}% current score)`,
      ``,
      `## Pending & Missing Requirements Breakdown`,
      ``,
      ...pendingList.map((item) =>
        [
          `### ⏳ ${item.id}: ${item.title} (${item.category})`,
          `- **Status:** ${item.status === "partial" ? "🟡 PARTIAL" : "❌ MISSING"}`,
          `- **Type:** ${item.type === "functional" ? "Functional Requirement" : "Non-Functional Requirement"}`,
          `- **Description:** ${item.description}`,
          item.evidence_files.length > 0
            ? `- **Partial Files Found:** ${item.evidence_files.join(", ")}`
            : `- **Evidence:** No implementation found in codebase`,
          item.remediation
            ? `- **Remediation Guide:** ${item.remediation}`
            : `- **Remediation Guide:** Implement feature in repository source code.`,
          ``,
        ]
          .filter(Boolean)
          .join("\n")
      ),
    ];

    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Pending_Gaps_Plan_${analysis.repository.replace("/", "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // Export Full Compliance Matrix
  function handleExportReport() {
    if (!analysis) return;
    const lines = [
      `# Requirements Compliance & Gap Analysis Report`,
      `**Repository:** ${analysis.repository}`,
      `**Specification Document:** ${analysis.fileName}`,
      `**Generated:** ${new Date(analysis.analyzedAt).toLocaleString()}`,
      `**Overall Completion Score:** ${analysis.overallScore}%`,
      `**Passed:** ${totalPassed} / ${totalReqs}`,
      `**Pending:** ${totalPending} / ${totalReqs}`,
      `**Functional Requirements:** ${analysis.functionalScore}% (${analysis.functionalCount.completed}/${analysis.functionalCount.total} passed)`,
      `**Non-Functional Compliance:** ${analysis.nonFunctionalScore}% (${analysis.nonFunctionalCount.completed}/${analysis.nonFunctionalCount.total} verified)`,
      ``,
      `## Summary`,
      analysis.summary,
      ``,
      `## Requirements Traceability Matrix`,
      ``,
      ...analysis.items.map((item) => {
        const icon =
          item.status === "completed" ? "✅ [PASSED]" : item.status === "partial" ? "🟡 [PARTIAL]" : "❌ [MISSING]";
        return [
          `### ${icon} ${item.id}: ${item.title} (${item.category})`,
          `- **Type:** ${item.type === "functional" ? "Functional Requirement" : "Non-Functional Requirement"}`,
          `- **Status:** ${item.status.toUpperCase()} (Confidence: ${(item.confidence * 100).toFixed(0)}%)`,
          `- **Description:** ${item.description}`,
          item.evidence_files.length > 0
            ? `- **Evidence Files:** ${item.evidence_files.join(", ")}`
            : `- **Evidence:** No implementation found in codebase`,
          item.evidence_snippet ? `- **Evidence Notes:**\n\`\`\`python\n${item.evidence_snippet}\n\`\`\`` : "",
          item.remediation ? `- **Remediation Guide:** ${item.remediation}` : "",
          ``,
        ]
          .filter(Boolean)
          .join("\n");
      }),
    ];

    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Requirements_Matrix_${analysis.repository.replace("/", "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <AnimatedContainer className="space-y-8 pb-16">
      {/* ── HEADER BANNER ── */}
      <AnimatedItem y={15}>
        <div className="rounded-3xl border border-border bg-surface p-6 sm:p-8 shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-2">
              <div className="flex items-center gap-2.5">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-teal/10 text-teal border border-teal/20">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                </div>
                <div>
                  <h1 className="text-2xl font-bold tracking-tight text-text">
                    Requirements & Traceability Matrix
                  </h1>
                  <p className="text-xs text-muted">
                    Track passed vs. pending specification requirements for each project, verified directly against codebase source files.
                  </p>
                </div>
              </div>
            </div>

            {/* Repo Selector & Re-analyze */}
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2 bg-canvas border border-border rounded-xl px-3 py-1.5 shadow-2xs">
                <span className="text-[11px] font-bold uppercase tracking-wider text-muted">Project:</span>
                <select
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="bg-transparent text-sm font-semibold text-text focus:outline-none cursor-pointer"
                >
                  {repos.map((r) => (
                    <option key={r.id} value={r.fullName} className="bg-surface text-text">
                      {r.fullName}
                    </option>
                  ))}
                </select>
              </div>

              {analysis && (
                <button
                  onClick={handleReanalyze}
                  disabled={uploading}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-teal/40 bg-teal/5 px-4 py-2 text-xs font-bold text-teal hover:border-teal hover:bg-teal/10 transition-all active:scale-95 disabled:opacity-50 shadow-2xs"
                  title="Re-verify requirements against latest REQUIREMENTS.md specification"
                >
                  <svg
                    className={`w-3.5 h-3.5 ${uploading ? "animate-spin" : ""}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                  Recheck REQUIREMENTS.md
                </button>
              )}
            </div>
          </div>
        </div>
      </AnimatedItem>

      {/* ── PROJECTS MEMORY / PASS RATE SUMMARY BAR ── */}
      {allSummaries.length > 0 && (
        <AnimatedItem y={18}>
          <div className="rounded-2xl border border-border bg-canvas/90 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-teal animate-pulse" />
                PROJECTS REQUIREMENTS MEMORY
              </p>
              <span className="text-[11px] text-muted font-medium">
                {allSummaries.length} {allSummaries.length === 1 ? "project" : "projects"} tracked
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {allSummaries.map((sum) => {
                const isSelected = selectedRepo === sum.repository;
                const pCount = sum.passedCount || 0;
                const tCount = sum.totalCount || 0;
                const pendCount = tCount - pCount;
                return (
                  <button
                    key={sum.repository}
                    onClick={() => setSelectedRepo(sum.repository)}
                    className={`text-left rounded-xl p-3.5 border transition-all ${
                      isSelected
                        ? "border-teal bg-surface shadow-xs ring-1 ring-teal/30"
                        : "border-border bg-surface/60 hover:bg-surface hover:border-teal/40"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <p className="text-xs font-bold text-text truncate">{sum.repository}</p>
                      <div className="flex items-center gap-1.5">
                        <span className="inline-flex items-center gap-1 text-[11px] font-extrabold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                          <span>✓</span> {pCount} Passed
                        </span>
                        {pendCount > 0 && (
                          <span className="inline-flex items-center gap-0.5 text-[10px] font-bold text-amber-800 bg-amber-50 px-1.5 py-0.5 rounded-md border border-amber-200">
                            {pendCount} Pend
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-muted">
                      <span className="truncate">📄 {sum.fileName}</span>
                      <span className="font-semibold text-text">{sum.overallScore}% score</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </AnimatedItem>
      )}

      {/* ── NOTIFICATIONS ── */}
      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs font-medium text-danger flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span>⚠</span>
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-danger hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {successMsg && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs font-medium text-emerald-800 flex items-center gap-2">
          <span>✓</span>
          <span>{successMsg}</span>
        </div>
      )}



      {/* ── DRAG & DROP PDF UPLOAD ZONE ── */}
      <AnimatedItem y={20}>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            if (e.dataTransfer.files && e.dataTransfer.files[0]) {
              handleFileUpload(e.dataTransfer.files[0]);
            }
          }}
          className={`relative rounded-3xl border-2 border-dashed p-7 text-center transition-all ${
            isDragging
              ? "border-teal bg-teal/5 scale-[1.01]"
              : "border-border bg-surface/60 hover:border-teal/50 hover:bg-surface"
          }`}
        >
          <input
            type="file"
            id="pdf-upload-input"
            accept=".pdf,application/pdf"
            className="hidden"
            disabled={uploading}
            onChange={(e) => {
              if (e.target.files && e.target.files[0]) {
                handleFileUpload(e.target.files[0]);
              }
            }}
          />

          {uploading ? (
            <div className="py-6 space-y-3">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-teal/10 text-teal animate-pulse">
                <svg className="w-6 h-6 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                </svg>
              </div>
              <p className="text-sm font-bold text-text">Analyzing Requirements & Codebase</p>
              <p className="text-xs text-muted max-w-md mx-auto">{uploadStep}</p>
            </div>
          ) : (
            <div className="py-3 space-y-4">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-teal/10 text-teal border border-teal/20">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
              </div>
              <div className="space-y-1">
                <p className="text-base font-bold text-text">Upload Requirements Document (PDF)</p>
                <p className="text-xs text-muted max-w-lg mx-auto">
                  Upload your Functional & Non-Functional Specifications (PRD, SRS, or Architecture Spec).
                  DocuBear parses requirements and verifies code completion via RAG and symbol analysis.
                </p>
              </div>
              <label
                htmlFor="pdf-upload-input"
                className="inline-flex items-center gap-2 cursor-pointer rounded-full bg-teal text-white px-6 py-2.5 text-xs font-bold shadow-xs hover:bg-teal/90 transition-all active:scale-95"
              >
                <span>📄</span>
                <span>Select PDF Document</span>
              </label>

              {analysis && (
                <div className="pt-2 text-xs text-muted flex flex-wrap items-center justify-center gap-2">
                  <span className="font-semibold text-text">Current Spec:</span>
                  <span className="font-mono font-bold bg-canvas px-2.5 py-1 rounded-md border border-border text-teal">
                    📄 {analysis.fileName}
                  </span>
                  <span>•</span>
                  <span className="font-semibold text-text">{analysis.items.length} total requirements parsed</span>
                  <span>•</span>
                  <span className="text-emerald-700 font-bold">✓ {totalPassed} Passed</span>
                  <span>•</span>
                  <span className="text-amber-700 font-bold">⏳ {totalPending} Pending</span>
                  <span>•</span>
                  <span>{new Date(analysis.analyzedAt).toLocaleDateString()}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </AnimatedItem>

      {/* ── ANALYSIS & STATUS DASHBOARD ── */}
      {analysis && (
        <>
          {/* ── INTERACTIVE STATUS STATS (CLICK TO FILTER) ── */}
          <AnimatedItem y={22}>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              {/* Passed Card */}
              <button
                onClick={() => {
                  setViewMode("list");
                  setActiveTab("passed");
                }}
                className={`p-4 sm:p-5 rounded-2xl border text-left transition-all relative overflow-hidden group ${
                  viewMode === "list" && activeTab === "passed"
                    ? "border-emerald-500 bg-emerald-50/70 shadow-sm ring-2 ring-emerald-500/30"
                    : "border-emerald-200/80 bg-emerald-50/30 hover:bg-emerald-50/60 hover:border-emerald-400"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-800 flex items-center gap-1.5">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-200/80 text-emerald-900 font-black text-xs">
                      ✓
                    </span>
                    Passed
                  </span>
                  <span className="text-xs font-bold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-md border border-emerald-300">
                    {totalReqs > 0 ? Math.round((totalPassed / totalReqs) * 100) : 0}%
                  </span>
                </div>
                <p className="text-3xl font-black text-emerald-900">{totalPassed}</p>
                <p className="text-[11px] text-emerald-700 mt-1 font-medium">Verified in codebase files</p>
                <div className="mt-2 text-[10px] font-bold text-emerald-800 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                  Click to view passed list →
                </div>
              </button>

              {/* Partial Card */}
              <button
                onClick={() => {
                  setViewMode("list");
                  setActiveTab("partial");
                }}
                className={`p-4 sm:p-5 rounded-2xl border text-left transition-all relative overflow-hidden group ${
                  viewMode === "list" && activeTab === "partial"
                    ? "border-amber-500 bg-amber-50/70 shadow-sm ring-2 ring-amber-500/30"
                    : "border-amber-200/80 bg-amber-50/30 hover:bg-amber-50/60 hover:border-amber-400"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-amber-800 flex items-center gap-1.5">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-200/80 text-amber-900 font-black text-xs">
                      ◐
                    </span>
                    Partial
                  </span>
                  <span className="text-xs font-bold text-amber-700 bg-amber-100/80 px-2 py-0.5 rounded-md border border-amber-300">
                    {totalReqs > 0 ? Math.round((totalPartial / totalReqs) * 100) : 0}%
                  </span>
                </div>
                <p className="text-3xl font-black text-amber-900">{totalPartial}</p>
                <p className="text-[11px] text-amber-700 mt-1 font-medium">Incomplete implementation</p>
                <div className="mt-2 text-[10px] font-bold text-amber-800 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                  Click to view partial list →
                </div>
              </button>

              {/* Missing / Pending Card */}
              <button
                onClick={() => {
                  setViewMode("list");
                  setActiveTab("pending");
                }}
                className={`p-4 sm:p-5 rounded-2xl border text-left transition-all relative overflow-hidden group ${
                  viewMode === "list" && activeTab === "pending"
                    ? "border-red-500 bg-red-50/70 shadow-sm ring-2 ring-red-500/30"
                    : "border-red-200/80 bg-red-50/30 hover:bg-red-50/60 hover:border-red-400"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-red-800 flex items-center gap-1.5">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-red-200/80 text-red-900 font-black text-xs">
                      ✕
                    </span>
                    Pending & Missing
                  </span>
                  <span className="text-xs font-bold text-red-700 bg-red-100/80 px-2 py-0.5 rounded-md border border-red-300">
                    {totalReqs > 0 ? Math.round((totalPending / totalReqs) * 100) : 0}%
                  </span>
                </div>
                <p className="text-3xl font-black text-danger">{totalPending}</p>
                <p className="text-[11px] text-red-700 mt-1 font-medium">
                  {totalMissing} missing + {totalPartial} partial
                </p>
                <div className="mt-2 text-[10px] font-bold text-danger opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                  Click to view pending items →
                </div>
              </button>

              {/* Total & Overall Compliance */}
              <button
                onClick={() => {
                  setViewMode("list");
                  setActiveTab("all");
                }}
                className={`p-4 sm:p-5 rounded-2xl border text-left transition-all relative overflow-hidden group ${
                  viewMode === "list" && activeTab === "all"
                    ? "border-teal bg-surface shadow-sm ring-2 ring-teal/30"
                    : "border-border bg-surface hover:border-teal/40"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-muted flex items-center gap-1.5">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-teal/15 text-teal font-black text-xs">
                      📊
                    </span>
                    Total Extracted
                  </span>
                  <span className="text-xs font-bold text-teal bg-teal/10 px-2 py-0.5 rounded-md border border-teal/20">
                    {analysis.overallScore}% score
                  </span>
                </div>
                <p className="text-3xl font-black text-text">{totalReqs}</p>
                <p className="text-[11px] text-muted mt-1 font-medium">
                  {analysis.functionalCount.total} FR + {analysis.nonFunctionalCount.total} NFR
                </p>
                <div className="mt-2 text-[10px] font-bold text-teal opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                  Click to view all requirements →
                </div>
              </button>
            </div>
          </AnimatedItem>

          {/* ── METRICS GAUGE & BREAKDOWN ── */}
          <AnimatedItem y={25}>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {/* Overall Completion Gauge */}
              <RadialMeter
                label="Overall Completion Score"
                percent={analysis.overallScore}
                displayValue={`${analysis.overallScore}%`}
                status={scoreStatus(analysis.overallScore)}
                sublabel={`${totalPassed} of ${totalReqs} Requirements Passed`}
              />

              {/* Functional Requirements Card */}
              <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Functional Specs (FR)</p>
                  <span className="text-xs font-extrabold text-teal">{analysis.functionalScore}%</span>
                </div>
                <p className="text-2xl font-bold text-text">
                  {analysis.functionalCount.completed}{" "}
                  <span className="text-sm font-normal text-muted">/ {analysis.functionalCount.total} Passed</span>
                </p>
                <div className="h-2.5 w-full bg-border rounded-full overflow-hidden flex">
                  <div
                    style={{ width: `${(analysis.functionalCount.completed / (analysis.functionalCount.total || 1)) * 100}%` }}
                    className="bg-emerald-600 h-full"
                    title="Passed"
                  />
                  <div
                    style={{ width: `${(analysis.functionalCount.partial / (analysis.functionalCount.total || 1)) * 100}%` }}
                    className="bg-yellow-400 h-full"
                    title="Partial"
                  />
                </div>
                <div className="flex items-center justify-between text-[11px] text-muted pt-1">
                  <span className="text-emerald-700 font-semibold">{analysis.functionalCount.completed} Passed</span>
                  <span className="text-yellow-700 font-semibold">{analysis.functionalCount.partial} Partial</span>
                  <span className="text-red-600 font-semibold">{analysis.functionalCount.missing} Missing</span>
                </div>
              </div>

              {/* Non-Functional Requirements Card */}
              <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Non-Functional Specs (NFR)</p>
                  <span className="text-xs font-extrabold text-teal">{analysis.nonFunctionalScore}%</span>
                </div>
                <p className="text-2xl font-bold text-text">
                  {analysis.nonFunctionalCount.completed}{" "}
                  <span className="text-sm font-normal text-muted">/ {analysis.nonFunctionalCount.total} Verified</span>
                </p>
                <div className="h-2.5 w-full bg-border rounded-full overflow-hidden flex">
                  <div
                    style={{
                      width: `${(analysis.nonFunctionalCount.completed / (analysis.nonFunctionalCount.total || 1)) * 100}%`,
                    }}
                    className="bg-emerald-600 h-full"
                    title="Passed"
                  />
                  <div
                    style={{
                      width: `${(analysis.nonFunctionalCount.partial / (analysis.nonFunctionalCount.total || 1)) * 100}%`,
                    }}
                    className="bg-yellow-400 h-full"
                    title="Partial"
                  />
                </div>
                <div className="flex items-center justify-between text-[11px] text-muted pt-1">
                  <span className="text-emerald-700 font-semibold">{analysis.nonFunctionalCount.completed} Passed</span>
                  <span className="text-yellow-700 font-semibold">{analysis.nonFunctionalCount.partial} Partial</span>
                  <span className="text-red-600 font-semibold">{analysis.nonFunctionalCount.missing} Missing</span>
                </div>
              </div>
            </div>
          </AnimatedItem>

          {/* ── AI SUMMARY & EXPORT BUTTONS ── */}
          <AnimatedItem y={30}>
            <div className="rounded-2xl border border-border bg-canvas p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <p className="text-[11px] font-bold uppercase tracking-wider text-teal">Executive Audit Summary</p>
                <p className="text-xs text-text/90 leading-relaxed max-w-3xl">{analysis.summary}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2.5 shrink-0 self-start md:self-auto">
                {totalPassed > 0 && (
                  <button
                    onClick={handleExportPassed}
                    className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 text-emerald-800 px-3.5 py-2 text-xs font-bold shadow-2xs hover:bg-emerald-100 transition-all active:scale-95"
                    title="Download Markdown of all passed requirements and code evidence"
                  >
                    <span>✓</span>
                    <span>Export Passed ({totalPassed})</span>
                  </button>
                )}
                {totalPending > 0 && (
                  <button
                    onClick={handleExportPending}
                    className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 text-amber-900 px-3.5 py-2 text-xs font-bold shadow-2xs hover:bg-amber-100 transition-all active:scale-95"
                    title="Download Markdown remediation plan for all pending requirements"
                  >
                    <span>⏳</span>
                    <span>Export Pending ({totalPending})</span>
                  </button>
                )}
                <button
                  onClick={handleExportReport}
                  className="inline-flex items-center gap-2 rounded-full bg-text text-white px-4 py-2 text-xs font-bold shadow-xs hover:bg-text/80 transition-all active:scale-95"
                  title="Download complete compliance matrix and gap analysis"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Export Matrix (.md)
                </button>
              </div>
            </div>
          </AnimatedItem>

          {/* ── PASSED VS. PENDING MAIN EXPLORER ── */}
          <AnimatedItem y={35}>
            <div className="rounded-3xl border border-border bg-surface p-6 sm:p-7 shadow-sm space-y-6">
              {/* Controls Bar: View Mode Switcher, Search, Category Selector */}
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-border pb-5">
                {/* View Mode Switcher */}
                <div className="flex items-center gap-1 bg-canvas p-1 rounded-xl border border-border">
                  <button
                    onClick={() => setViewMode("split")}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      viewMode === "split" ? "bg-teal text-white shadow-xs" : "text-muted hover:text-text"
                    }`}
                  >
                    <span>🔀</span>
                    <span>Side-by-Side (Passed vs Pending)</span>
                  </button>
                  <button
                    onClick={() => setViewMode("list")}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      viewMode === "list" ? "bg-teal text-white shadow-xs" : "text-muted hover:text-text"
                    }`}
                  >
                    <span>📑</span>
                    <span>Tabbed List</span>
                  </button>
                  <button
                    onClick={() => setViewMode("table")}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      viewMode === "table" ? "bg-teal text-white shadow-xs" : "text-muted hover:text-text"
                    }`}
                  >
                    <span>📋</span>
                    <span>Traceability Matrix</span>
                  </button>
                </div>

                {/* Search & Category Filter */}
                <div className="flex flex-wrap items-center gap-3">
                  {categories.length > 0 && (
                    <select
                      value={selectedCategory}
                      onChange={(e) => setSelectedCategory(e.target.value)}
                      className="bg-canvas border border-border text-xs font-semibold text-text rounded-xl px-3 py-2 focus:outline-none"
                    >
                      <option value="all">All Categories ({categories.length})</option>
                      {categories.map((cat) => (
                        <option key={cat} value={cat}>
                          {cat}
                        </option>
                      ))}
                    </select>
                  )}

                  <div className="relative">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search requirements or code files..."
                      className="bg-canvas border border-border text-xs text-text placeholder:text-muted rounded-xl pl-8 pr-3 py-2 w-64 focus:outline-none focus:ring-2 focus:ring-teal/30"
                    />
                    <svg
                      className="w-3.5 h-3.5 text-muted absolute left-2.5 top-1/2 -translate-y-1/2"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  </div>
                </div>
              </div>

              {/* ────────────────────────────────────────────────────────── */}
              {/* MODE 1: SIDE-BY-SIDE SPLIT VIEW (PASSED VS PENDING)        */}
              {/* ────────────────────────────────────────────────────────── */}
              {viewMode === "split" && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
                  {/* LEFT COLUMN: PASSED REQUIREMENTS */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-3.5 rounded-2xl bg-emerald-50/80 border border-emerald-200">
                      <div className="flex items-center gap-2">
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-600 text-white font-extrabold text-xs">
                          ✓
                        </span>
                        <div>
                          <h2 className="text-sm font-bold text-emerald-950">Passed Requirements</h2>
                          <p className="text-[11px] text-emerald-800">Verified implementations found in codebase</p>
                        </div>
                      </div>
                      <span className="text-xs font-extrabold text-emerald-900 bg-white px-2.5 py-1 rounded-full border border-emerald-300 shadow-2xs">
                        {passedItems.length} passed
                      </span>
                    </div>

                    {passedItems.length === 0 ? (
                      <div className="py-12 text-center text-muted text-xs border border-dashed border-border rounded-2xl p-6">
                        No passed requirements match your current search or category filter.
                      </div>
                    ) : (
                      <div className="space-y-3.5">
                        {passedItems.map((item) => (
                          <div
                            key={item.id}
                            className="rounded-2xl border border-emerald-200 bg-emerald-50/20 hover:border-emerald-300 p-4 space-y-3 transition-all shadow-2xs"
                          >
                            <div className="flex items-center justify-between gap-2 flex-wrap">
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-xs font-extrabold px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-900 border border-emerald-300">
                                  {item.id}
                                </span>
                                <span className="text-[10px] font-bold uppercase tracking-wider text-muted truncate max-w-[180px]">
                                  {item.category}
                                </span>
                              </div>
                              <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-100/80 text-emerald-900 border border-emerald-300">
                                <span>✓ PASSED</span>
                                <span className="text-[10px] opacity-75">({(item.confidence * 100).toFixed(0)}%)</span>
                              </span>
                            </div>

                            <div>
                              <h3 className="text-xs font-bold text-text">{item.title}</h3>
                              <p className="text-[11px] text-muted mt-0.5 leading-relaxed">{item.description}</p>
                            </div>

                            {/* Verified Source Files */}
                            {item.evidence_files && item.evidence_files.length > 0 && (
                              <div className="pt-2 border-t border-emerald-200/60 space-y-1.5">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-800">
                                  Verified Evidence Files:
                                </span>
                                <div className="flex flex-wrap gap-1.5">
                                  {item.evidence_files.map((file) => (
                                    <span
                                      key={file}
                                      className="font-mono text-[10px] px-2 py-0.5 rounded bg-white border border-emerald-200 text-emerald-800 font-semibold"
                                    >
                                      📄 {file}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Code Snippet if present */}
                            {item.evidence_snippet && (
                              <div className="pt-1">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-muted block mb-1">
                                  Code Implementation Snippet:
                                </span>
                                <pre className="text-[10px] text-text font-mono bg-canvas p-2.5 rounded-lg border border-border overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-36">
                                  {item.evidence_snippet}
                                </pre>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* RIGHT COLUMN: PENDING & MISSING REQUIREMENTS */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-3.5 rounded-2xl bg-red-50/80 border border-red-200">
                      <div className="flex items-center gap-2">
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-600 text-white font-extrabold text-xs">
                          ⏳
                        </span>
                        <div>
                          <h2 className="text-sm font-bold text-red-950">Pending & Missing Requirements</h2>
                          <p className="text-[11px] text-red-800">Gaps requiring code implementation or completion</p>
                        </div>
                      </div>
                      <span className="text-xs font-extrabold text-red-900 bg-white px-2.5 py-1 rounded-full border border-red-300 shadow-2xs">
                        {pendingItems.length} pending
                      </span>
                    </div>

                    {pendingItems.length === 0 ? (
                      <div className="py-12 text-center text-emerald-800 font-semibold text-xs border border-dashed border-emerald-200 bg-emerald-50/30 rounded-2xl p-6">
                        🎉 All requirements in this category have passed!
                      </div>
                    ) : (
                      <div className="space-y-3.5">
                        {pendingItems.map((item) => {
                          const isPartial = item.status === "partial";
                          return (
                            <div
                              key={item.id}
                              className={`rounded-2xl border p-4 space-y-3 transition-all shadow-2xs ${
                                isPartial
                                  ? "border-amber-200 bg-amber-50/20 hover:border-amber-300"
                                  : "border-red-200 bg-red-50/15 hover:border-red-300"
                              }`}
                            >
                              <div className="flex items-center justify-between gap-2 flex-wrap">
                                <div className="flex items-center gap-2">
                                  <span
                                    className={`font-mono text-xs font-extrabold px-2 py-0.5 rounded-md border ${
                                      isPartial
                                        ? "bg-amber-100 text-amber-900 border-amber-300"
                                        : "bg-red-100 text-danger border-red-200"
                                    }`}
                                  >
                                    {item.id}
                                  </span>
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted truncate max-w-[180px]">
                                    {item.category}
                                  </span>
                                </div>
                                <span
                                  className={`inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${
                                    isPartial
                                      ? "bg-amber-100 text-amber-900 border-amber-300"
                                      : "bg-red-100 text-danger border-red-200"
                                  }`}
                                >
                                  <span>{isPartial ? "🟡 PARTIAL" : "✕ MISSING"}</span>
                                  <span className="text-[10px] opacity-75">({(item.confidence * 100).toFixed(0)}%)</span>
                                </span>
                              </div>

                              <div>
                                <h3 className="text-xs font-bold text-text">{item.title}</h3>
                                <p className="text-[11px] text-muted mt-0.5 leading-relaxed">{item.description}</p>
                              </div>

                              {/* Partial files if any */}
                              {item.evidence_files && item.evidence_files.length > 0 && (
                                <div className="pt-2 border-t border-border/60 space-y-1">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-amber-800">
                                    Related Code Files:
                                  </span>
                                  <div className="flex flex-wrap gap-1.5">
                                    {item.evidence_files.map((file) => (
                                      <span
                                        key={file}
                                        className="font-mono text-[10px] px-2 py-0.5 rounded bg-white border border-amber-200 text-amber-900 font-semibold"
                                      >
                                        📄 {file}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Actionable Remediation Guide */}
                              {item.remediation && (
                                <div className="text-[11px] text-amber-950 bg-amber-100/60 p-2.5 rounded-lg border border-amber-200/80 flex items-start gap-2">
                                  <span className="font-bold text-amber-900 shrink-0">Remediation Guide:</span>
                                  <span className="leading-relaxed">{item.remediation}</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ────────────────────────────────────────────────────────── */}
              {/* MODE 2: TABBED LIST VIEW                                   */}
              {/* ────────────────────────────────────────────────────────── */}
              {viewMode === "list" && (
                <div className="space-y-6">
                  {/* Filter Tabs */}
                  <div className="flex flex-wrap items-center gap-1.5 bg-canvas p-1 rounded-xl border border-border">
                    <button
                      onClick={() => setActiveTab("passed")}
                      className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        activeTab === "passed"
                          ? "bg-emerald-600 text-white shadow-xs"
                          : "text-emerald-700 hover:bg-emerald-50"
                      }`}
                    >
                      <span>✓ Passed</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                          activeTab === "passed" ? "bg-white/20 text-white" : "bg-emerald-100 text-emerald-800"
                        }`}
                      >
                        {totalPassed}
                      </span>
                    </button>

                    <button
                      onClick={() => setActiveTab("pending")}
                      className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        activeTab === "pending" ? "bg-danger text-white shadow-xs" : "text-danger hover:bg-red-50"
                      }`}
                    >
                      <span>✕ Pending & Missing</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                          activeTab === "pending" ? "bg-white/20 text-white" : "bg-red-100 text-danger"
                        }`}
                      >
                        {totalPending}
                      </span>
                    </button>

                    <button
                      onClick={() => setActiveTab("partial")}
                      className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        activeTab === "partial" ? "bg-amber-500 text-white shadow-xs" : "text-amber-800 hover:bg-amber-50"
                      }`}
                    >
                      <span>◐ Partial</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                          activeTab === "partial" ? "bg-white/20 text-white" : "bg-amber-100 text-amber-900"
                        }`}
                      >
                        {totalPartial}
                      </span>
                    </button>

                    <button
                      onClick={() => setActiveTab("functional")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        activeTab === "functional" ? "bg-surface text-teal shadow-xs" : "text-muted hover:text-text"
                      }`}
                    >
                      Functional ({analysis.functionalCount.total})
                    </button>

                    <button
                      onClick={() => setActiveTab("non_functional")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        activeTab === "non_functional" ? "bg-surface text-teal shadow-xs" : "text-muted hover:text-text"
                      }`}
                    >
                      Non-Functional ({analysis.nonFunctionalCount.total})
                    </button>

                    <button
                      onClick={() => setActiveTab("all")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        activeTab === "all" ? "bg-surface text-text shadow-xs" : "text-muted hover:text-text"
                      }`}
                    >
                      All ({analysis.items.length})
                    </button>
                  </div>

                  {/* Requirements List */}
                  {filteredItems.length === 0 ? (
                    <div className="py-12 text-center text-muted text-xs border border-dashed border-border rounded-2xl p-6">
                      No requirements found matching the current filter.
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {filteredItems.map((item) => {
                        const isCompleted = item.status === "completed";
                        const isPartial = item.status === "partial";

                        return (
                          <div
                            key={item.id}
                            className={`rounded-2xl border p-5 transition-all space-y-3 ${
                              isCompleted
                                ? "border-emerald-200 bg-emerald-50/20 hover:border-emerald-300"
                                : isPartial
                                ? "border-amber-200 bg-amber-50/15 hover:border-amber-300"
                                : "border-border bg-surface hover:border-teal/40"
                            }`}
                          >
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                              <div className="flex items-center gap-2.5 flex-wrap">
                                <span
                                  className={`font-mono text-xs font-extrabold px-2.5 py-1 rounded-lg border ${
                                    isCompleted
                                      ? "bg-emerald-100 text-emerald-900 border-emerald-300"
                                      : isPartial
                                      ? "bg-amber-100 text-amber-900 border-amber-300"
                                      : "bg-teal/10 text-teal border-teal/20"
                                  }`}
                                >
                                  {item.id}
                                </span>
                                <span className="text-xs font-bold uppercase tracking-wider text-muted">
                                  {item.category}
                                </span>
                                <span className="text-[10px] px-2 py-0.5 rounded-full border border-border bg-canvas text-muted">
                                  {item.type === "functional" ? "Functional" : "Non-Functional"}
                                </span>
                              </div>

                              <span
                                className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full border self-start sm:self-auto ${
                                  isCompleted
                                    ? "bg-emerald-50 text-emerald-800 border-emerald-300 shadow-2xs"
                                    : isPartial
                                    ? "bg-amber-50 text-amber-800 border-amber-300"
                                    : "bg-red-50 text-danger border-red-200"
                                }`}
                              >
                                <span>{isCompleted ? "✓" : isPartial ? "◐" : "✕"}</span>
                                <span>
                                  {isCompleted
                                    ? "Verified Passed"
                                    : isPartial
                                    ? "Partially Implemented"
                                    : "Pending Implementation"}
                                </span>
                                <span className="text-[10px] opacity-75">({(item.confidence * 100).toFixed(0)}%)</span>
                              </span>
                            </div>

                            <div>
                              <h3 className="text-sm font-bold text-text">{item.title}</h3>
                              <p className="text-xs text-muted mt-1 leading-relaxed">{item.description}</p>
                            </div>

                            {/* Code Evidence Section */}
                            <div className="pt-2 border-t border-border/60 text-xs space-y-2">
                              {item.evidence_files && item.evidence_files.length > 0 ? (
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-[11px] font-bold text-emerald-800">Verified Files:</span>
                                  {item.evidence_files.map((filePath) => (
                                    <span
                                      key={filePath}
                                      className="font-mono text-[11px] px-2.5 py-0.5 rounded-md bg-canvas border border-emerald-200 text-emerald-800 font-semibold"
                                    >
                                      📄 {filePath}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <div className="text-[11px] text-muted italic">
                                  No code implementation found in repository files.
                                </div>
                              )}

                              {item.evidence_snippet && (
                                <div className="space-y-1">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
                                    Verified Implementation:
                                  </span>
                                  <pre className="text-[11px] text-text font-mono bg-canvas p-3 rounded-xl border border-border overflow-x-auto whitespace-pre-wrap leading-relaxed">
                                    {item.evidence_snippet}
                                  </pre>
                                </div>
                              )}

                              {item.status !== "completed" && item.remediation && (
                                <div className="text-[11px] text-amber-900 bg-amber-50/70 p-3 rounded-xl border border-amber-200/70 flex items-start gap-2">
                                  <span className="font-bold text-amber-800 shrink-0">Remediation Guide:</span>
                                  <span className="leading-relaxed">{item.remediation}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ────────────────────────────────────────────────────────── */}
              {/* MODE 3: TRACEABILITY MATRIX / COMPACT TABLE VIEW           */}
              {/* ────────────────────────────────────────────────────────── */}
              {viewMode === "table" && (
                <div className="overflow-x-auto rounded-2xl border border-border bg-canvas/40">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border bg-canvas text-muted text-[11px] font-bold uppercase tracking-wider">
                        <th className="py-3 px-4">Req ID</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4">Category & Title</th>
                        <th className="py-3 px-4">Type</th>
                        <th className="py-3 px-4">Verified Evidence / Remediation</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {filteredItems.map((item) => {
                        const isCompleted = item.status === "completed";
                        const isPartial = item.status === "partial";
                        return (
                          <tr
                            key={item.id}
                            className={`hover:bg-surface/90 transition-colors ${
                              isCompleted ? "bg-emerald-50/10" : isPartial ? "bg-amber-50/10" : "bg-transparent"
                            }`}
                          >
                            <td className="py-3.5 px-4 font-mono font-bold whitespace-nowrap">
                              <span
                                className={`px-2 py-0.5 rounded text-[11px] font-extrabold border ${
                                  isCompleted
                                    ? "bg-emerald-100 text-emerald-900 border-emerald-300"
                                    : isPartial
                                    ? "bg-amber-100 text-amber-900 border-amber-300"
                                    : "bg-red-100 text-danger border-red-200"
                                }`}
                              >
                                {item.id}
                              </span>
                            </td>

                            <td className="py-3.5 px-4 whitespace-nowrap">
                              <span
                                className={`inline-flex items-center gap-1 font-bold text-[11px] px-2.5 py-0.5 rounded-full border ${
                                  isCompleted
                                    ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                                    : isPartial
                                    ? "bg-amber-50 text-amber-800 border-amber-300"
                                    : "bg-red-50 text-danger border-red-200"
                                }`}
                              >
                                <span>{isCompleted ? "✓ PASSED" : isPartial ? "◐ PARTIAL" : "✕ MISSING"}</span>
                              </span>
                            </td>

                            <td className="py-3.5 px-4">
                              <div className="space-y-0.5">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-muted block">
                                  {item.category}
                                </span>
                                <p className="font-bold text-text">{item.title}</p>
                                <p className="text-[11px] text-muted line-clamp-1">{item.description}</p>
                              </div>
                            </td>

                            <td className="py-3.5 px-4 whitespace-nowrap">
                              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-canvas border border-border text-muted">
                                {item.type === "functional" ? "FR" : "NFR"}
                              </span>
                            </td>

                            <td className="py-3.5 px-4 max-w-xs">
                              {isCompleted ? (
                                <div className="space-y-1">
                                  {item.evidence_files.length > 0 ? (
                                    <div className="flex flex-wrap gap-1">
                                      {item.evidence_files.map((f) => (
                                        <span key={f} className="font-mono text-[10px] text-emerald-800 font-semibold">
                                          📄 {f}
                                        </span>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-[11px] text-emerald-700">Verified</span>
                                  )}
                                </div>
                              ) : (
                                <p className="text-[11px] text-amber-900 line-clamp-2">
                                  {item.remediation || "Needs implementation in repository"}
                                </p>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </AnimatedItem>
        </>
      )}

      {/* ── EMPTY STATE ── */}
      {!analysis && !loading && !uploading && (
        <AnimatedItem y={25}>
          <div className="rounded-3xl border border-dashed border-border bg-surface/50 p-12 text-center space-y-3">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-teal/10 text-teal">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <h2 className="text-base font-bold text-text">No Requirements Document Uploaded Yet</h2>
            <p className="text-xs text-muted max-w-md mx-auto">
              Upload a project specification PDF (PRD, SRS, or Requirements Document) in the dropzone above to track
              functional and non-functional completion against this repository.
            </p>
          </div>
        </AnimatedItem>
      )}
    </AnimatedContainer>
  );
}

export default function RequirementsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-xs text-muted">Loading Requirements Hub...</div>}>
      <RequirementsContent />
    </Suspense>
  );
}
