"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import FileTreePanel, { FileTreeNode } from "@/components/FileTreePanel";
import DocPreview from "@/components/DocPreview";
import ApprovalActions from "@/components/ApprovalActions";
import { DiffSummary } from "@/components/DiffViewer";
import { AnimatedContainer, AnimatedItem } from "@/components/AnimatedItem";
import { Repo, FileDocVersion, FileDocSummary } from "@/types";
import { useRegisterOpenDocument } from "@/lib/agentContext";

const REPO_STORAGE_KEY = "docubear_filedocs_repo";

export default function FileDocsPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [tree, setTree] = useState<FileTreeNode | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState<string | null>(null);

  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [doc, setDoc] = useState<FileDocVersion | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  const [generatedDocs, setGeneratedDocs] = useState<FileDocSummary[]>([]);
  const [generatedDocsLoading, setGeneratedDocsLoading] = useState(false);

  // Load repos once, then restore the last-selected repo if it still exists.
  useEffect(() => {
    fetch("/api/repos")
      .then((res) => res.json())
      .then((data: Repo[]) => {
        setRepos(data);
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
      })
      .catch(() => setRepos([]));
  }, []);

  const fetchTree = useCallback((repository: string) => {
    setTreeLoading(true);
    setTreeError(null);
    setTree(null);
    fetch(`/api/files/tree?repository=${encodeURIComponent(repository)}`)
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error || "Failed to load file tree");
        setTree(data as FileTreeNode);
      })
      .catch((err) => setTreeError(err instanceof Error ? err.message : "Failed to load file tree"))
      .finally(() => setTreeLoading(false));
  }, []);

  const fetchGeneratedDocs = useCallback((repository: string) => {
    setGeneratedDocsLoading(true);
    fetch(`/api/files/docs?repository=${encodeURIComponent(repository)}`)
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error || "Failed to load generated docs");
        setGeneratedDocs(data as FileDocSummary[]);
      })
      .catch(() => setGeneratedDocs([]))
      .finally(() => setGeneratedDocsLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedRepo) return;
    try {
      window.localStorage.setItem(REPO_STORAGE_KEY, selectedRepo);
    } catch {
      // Storage unavailable — selection just won't survive navigation.
    }
    setSelectedPath(null);
    setDoc(null);
    setDocError(null);
    fetchTree(selectedRepo);
    fetchGeneratedDocs(selectedRepo);
  }, [selectedRepo, fetchTree, fetchGeneratedDocs]);

  const documentedPaths = useMemo(
    () => new Set(generatedDocs.map((d) => d.sourcePath)),
    [generatedDocs]
  );

  const generateDoc = useCallback(
    (path: string, force: boolean) => {
      if (!selectedRepo) return;
      if (force) setRegenerating(true);
      else {
        setDocLoading(true);
        setDoc(null);
      }
      setDocError(null);

      fetch("/api/files/generate-doc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repository: selectedRepo, path, force }),
      })
        .then(async (res) => {
          const data = await res.json();
          if (!res.ok) throw new Error(data?.error || "Failed to generate documentation");
          setDoc(data as FileDocVersion);
          fetchGeneratedDocs(selectedRepo);
        })
        .catch((err) => setDocError(err instanceof Error ? err.message : "Failed to generate documentation"))
        .finally(() => {
          setDocLoading(false);
          setRegenerating(false);
        });
    },
    [selectedRepo, fetchGeneratedDocs]
  );

  const handleSelectFile = (path: string) => {
    setSelectedPath(path);
    generateDoc(path, false);
  };

  const handleRegenerate = () => {
    if (selectedPath) generateDoc(selectedPath, true);
  };

  const handleApprove = () => {
    setDoc((prev) => (prev ? { ...prev, previousContent: undefined, hasChanges: false, status: "approved" } : prev));
  };

  const handleRevise = (updatedDoc: any) => {
    if (updatedDoc?.content) {
      setDoc((prev) =>
        prev
          ? {
              ...prev,
              content: updatedDoc.content,
              previousContent: updatedDoc.previous_content || updatedDoc.previousContent || prev.content,
              hasChanges: Boolean(updatedDoc.previous_content || updatedDoc.previousContent),
              status: "changes_requested",
            }
          : prev
      );
    }
  };

  const handleSave = (updatedDoc: any) => {
    if (updatedDoc?.content) {
      setDoc((prev) =>
        prev
          ? {
              ...prev,
              content: updatedDoc.content,
              previousContent: updatedDoc.previous_content || updatedDoc.previousContent || prev.previousContent,
              hasChanges: Boolean(updatedDoc.previous_content || updatedDoc.previousContent || prev.previousContent),
            }
          : prev
      );
    }
  };

  const handleAssistantChange = (newContent: string, previousContent: string) => {
    setDoc((prev) =>
      prev
        ? {
            ...prev,
            content: newContent,
            previousContent,
            hasChanges: true,
            status: "changes_requested",
          }
        : prev
    );
  };

  const fileName = doc?.title.split("/").at(-1) || "";
  const repositoryName = selectedRepo;

  // Tell the persistent, layout-level AgentSidebar which document is open —
  // it lives outside this page so it survives navigation instead of being
  // torn down and rebuilt every time.
  useRegisterOpenDocument(
    repositoryName
      ? {
          repositoryName,
          documentId: doc?.id,
          documentTitle: fileName || undefined,
          documentContent: doc?.content,
          onDocumentChanged: handleAssistantChange,
        }
      : null
  );

  return (
    <div className="flex flex-col gap-6">
      <AnimatedItem y={12}>
        <div className="relative overflow-hidden rounded-2xl border border-border bg-surface p-6 shadow-sm">
          <div className="absolute top-0 left-0 right-0 h-1 bg-presidio-gradient" />
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">FILE DOCUMENTATION</span>
              <h1 className="text-xl font-bold tracking-tight text-text">Generate Docs for a Single File</h1>
              <p className="text-xs text-muted max-w-xl leading-relaxed">
                Browse a repository's file tree and generate accurate, RAG-grounded documentation for any one file — including its dependencies, imports, and exports.
              </p>
            </div>

            <div className="flex items-center gap-2 self-start md:self-auto">
              <select
                value={selectedRepo}
                onChange={(e) => setSelectedRepo(e.target.value)}
                className="rounded-full border border-border bg-canvas px-4 py-2 text-xs font-semibold text-text transition-all focus:border-teal focus:bg-surface focus:outline-none focus:ring-2 focus:ring-teal/20 min-w-[14rem]"
              >
                {repos.length === 0 && <option value="">No repositories connected</option>}
                {repos.map((r) => (
                  <option key={r.id} value={r.fullName}>{r.fullName}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </AnimatedItem>

      <div className="flex flex-col lg:flex-row gap-6 items-start">
        <aside className="lg:sticky lg:top-24 lg:self-start flex-shrink-0 w-full lg:w-auto">
          <FileTreePanel
            tree={tree}
            loading={treeLoading}
            error={treeError}
            selectedPath={selectedPath}
            onSelectFile={handleSelectFile}
            documentedPaths={documentedPaths}
          />
        </aside>

        <section className="min-w-0 flex-1 w-full">
          {!selectedPath && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-surface/50 p-16 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-teal/10 text-teal mb-3">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-sm font-bold text-text">Select a file to document</p>
              <p className="mt-1 text-xs text-muted max-w-sm">
                Pick any source file from the tree on the left. Its documentation will be generated on first click, and reused instantly after that.
              </p>
            </div>
          )}

          {selectedPath && docLoading && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-surface p-16 text-center">
              <svg className="w-6 h-6 animate-spin text-teal mb-3" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <p className="text-xs font-semibold text-muted">Generating documentation for {selectedPath}...</p>
            </div>
          )}

          {selectedPath && !docLoading && docError && (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
              <p className="text-sm font-bold text-red-800">Couldn't generate documentation</p>
              <p className="mt-1 text-xs text-red-700">{docError}</p>
              <button
                onClick={() => selectedPath && generateDoc(selectedPath, false)}
                className="mt-4 rounded-full bg-red-700 text-white text-xs font-bold uppercase tracking-wider px-5 py-2 hover:bg-red-800 transition-colors"
              >
                Retry
              </button>
            </div>
          )}

          {selectedPath && !docLoading && !docError && doc && (
            <AnimatedContainer className="space-y-6 pb-12">
              <AnimatedItem y={15}>
                <div className="relative overflow-hidden rounded-2xl border border-border bg-surface p-6 shadow-sm">
                  <div className="absolute top-0 left-0 right-0 h-1 bg-presidio-gradient" />
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="space-y-1.5 min-w-0">
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">FILE DOCUMENTATION</span>
                        {doc.previousContent && (
                          <DiffSummary oldText={doc.previousContent} newText={doc.content} />
                        )}
                      </div>
                      <h1 className="text-2xl font-extrabold tracking-tight text-text truncate">{fileName}</h1>
                      <p className="text-xs font-mono text-muted truncate opacity-80">{doc.sourcePath}</p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0 self-start md:self-auto">
                      <button
                        onClick={handleRegenerate}
                        disabled={regenerating}
                        className="inline-flex items-center gap-1.5 rounded-full border border-teal/30 bg-teal/10 text-teal text-xs font-bold uppercase tracking-wider px-4 py-2 hover:bg-teal hover:text-white transition-all disabled:opacity-50"
                      >
                        {regenerating ? (
                          <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                          </svg>
                        ) : (
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                        )}
                        Regenerate
                      </button>
                    </div>
                  </div>

                  {(doc.imports.length > 0 || doc.exports.length > 0) && (
                    <div className="mt-4 flex flex-wrap gap-4 border-t border-border pt-4">
                      {doc.imports.length > 0 && (
                        <div className="min-w-0">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1.5">Imports ({doc.imports.length})</p>
                          <div className="flex flex-wrap gap-1.5">
                            {doc.imports.slice(0, 8).map((imp, i) => (
                              <span key={i} className="rounded-full border border-border bg-canvas px-2.5 py-0.5 text-[10px] font-mono text-text/80 truncate max-w-[16rem]">
                                {imp}
                              </span>
                            ))}
                            {doc.imports.length > 8 && (
                              <span className="text-[10px] text-muted self-center">+{doc.imports.length - 8} more</span>
                            )}
                          </div>
                        </div>
                      )}
                      {doc.exports.length > 0 && (
                        <div className="min-w-0">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1.5">Exports ({doc.exports.length})</p>
                          <div className="flex flex-wrap gap-1.5">
                            {doc.exports.slice(0, 8).map((exp, i) => (
                              <span key={i} className="rounded-full border border-teal/20 bg-teal/5 px-2.5 py-0.5 text-[10px] font-mono text-teal truncate max-w-[16rem]">
                                {exp}
                              </span>
                            ))}
                            {doc.exports.length > 8 && (
                              <span className="text-[10px] text-muted self-center">+{doc.exports.length - 8} more</span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {doc.warnings.length > 0 && (
                    <div className="mt-4 rounded-xl border border-yellow-300 bg-yellow-50 px-4 py-2.5">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-yellow-800 mb-1">Quality notice</p>
                      <ul className="text-[11px] text-yellow-800 space-y-0.5 list-disc list-inside">
                        {doc.warnings.map((w, i) => <li key={i}>{w}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              </AnimatedItem>

              <AnimatedItem y={20}>
                <ApprovalActions docId={doc.id} onApprove={handleApprove} onRevise={handleRevise} />
              </AnimatedItem>

              <AnimatedItem y={25}>
                <DocPreview
                  key={`${doc.id}-${doc.previousContent ? "diff" : "clean"}-${doc.content.length}`}
                  docId={doc.id}
                  content={doc.content}
                  previousContent={doc.previousContent}
                  onSave={handleSave}
                />
              </AnimatedItem>
            </AnimatedContainer>
          )}
        </section>
      </div>

      {!generatedDocsLoading && generatedDocs.length > 0 && (
        <AnimatedItem y={12}>
          <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">History</span>
                <p className="mt-0.5 text-xs text-muted">
                  Every file documented so far for this repository — click one to reopen it instantly.
                </p>
              </div>
              <span className="flex-shrink-0 rounded-full border border-border bg-canvas px-2.5 py-0.5 text-[10px] font-bold text-muted">
                {generatedDocs.length}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {generatedDocs.map((d) => (
                <button
                  key={d.id}
                  onClick={() => handleSelectFile(d.sourcePath)}
                  className={`flex items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-left transition-colors ${
                    selectedPath === d.sourcePath
                      ? "border-teal/40 bg-teal/5"
                      : "border-border bg-canvas hover:border-teal/40 hover:bg-teal/5"
                  }`}
                >
                  <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-teal/10 text-teal">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-semibold text-text">
                      {d.sourcePath.split("/").at(-1)}
                    </span>
                    <span className="block truncate text-[10px] font-mono text-muted">
                      {d.sourcePath}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </AnimatedItem>
      )}
    </div>
  );
}
