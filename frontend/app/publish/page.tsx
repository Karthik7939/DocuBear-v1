"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

import { AnimatedContainer, AnimatedItem } from "@/components/AnimatedItem";

interface RepoItem {
  id: string;
  fullName: string;
}

interface StandardDocSummary {
  id: string;
  repo_id: string;
  title: string;
  source_path: string;
}

// Fetched directly from the FastAPI backend (see the fetch below), which
// returns snake_case field names -- unlike /api/files/docs (the Next.js
// proxy the /file-docs page goes through), which converts to camelCase.
interface FileDocSummary {
  id: string;
  repo_id: string;
  title: string;
  source_path: string;
}

/** One selectable row in the "choose documents" list, shared by both the
 *  GitBook publish action and the PDF export action below it. */
interface PublishableDoc {
  key: string;
  /** Path relative to generated_docs/<repo_slug>/, as expected by both
   *  /api/gitbook/publish-repo and /api/export/generate. */
  filename: string;
  label: string;
  sublabel: string;
  kind: "standard" | "file";
}

interface ExportRecord {
  id: string;
  repository_name: string;
  repo_slug: string;
  download_filename: string;
  title: string;
  documents: string[];
  created_at: string;
  size_bytes: number;
}

const BACKEND_BASE = "http://127.0.0.1:8000";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function downloadUrlFor(record: Pick<ExportRecord, "repo_slug" | "id">): string {
  return `${BACKEND_BASE}/api/export/download/${encodeURIComponent(record.repo_slug)}/${encodeURIComponent(record.id)}`;
}

export default function PublishPage() {
  const [apiToken, setApiToken] = useState<string>("");
  const [showToken, setShowToken] = useState<boolean>(false);
  const [spaceId, setSpaceId] = useState<string>("");
  const [publicBaseUrl, setPublicBaseUrl] = useState<string>("");
  const [repos, setRepos] = useState<RepoItem[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");

  const [testingConnection, setTestingConnection] = useState<boolean>(false);
  const [connectionStatus, setConnectionStatus] = useState<{ success: boolean; message: string } | null>(null);

  const [publishing, setPublishing] = useState<boolean>(false);
  const [publishResult, setPublishResult] = useState<any>(null);

  const [standardDocs, setStandardDocs] = useState<PublishableDoc[]>([]);
  const [fileDocs, setFileDocs] = useState<PublishableDoc[]>([]);
  const [docsLoading, setDocsLoading] = useState<boolean>(false);
  // Shared by both actions below -- one list of checkboxes, two things you
  // can do with what's checked, rather than two separate (and previously
  // near-identical-looking) document lists.
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());

  const [exporting, setExporting] = useState<boolean>(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportHistory, setExportHistory] = useState<ExportRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);

  // Load saved settings from localStorage and fetch connected repos
  useEffect(() => {
    const savedToken = localStorage.getItem("docubear_gitbook_token") || "";
    const savedSpaceId = localStorage.getItem("docubear_gitbook_space_id") || "";
    const savedPublicUrl = localStorage.getItem("docubear_gitbook_public_url") || "";
    setApiToken(savedToken);
    setSpaceId(savedSpaceId);
    setPublicBaseUrl(savedPublicUrl);

    // Fetch repos
    fetch(`${BACKEND_BASE}/api/documents/repos`)
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) {
          const list = data.map((r: string) => ({ id: r, fullName: r }));
          setRepos(list);
          if (list.length > 0) {
            setSelectedRepo(list[0].fullName);
          }
        }
      })
      .catch(() => {
        // Fallback default repo if offline
        setRepos([{ id: "Karthik7939/Mindstride-test-repo-v1", fullName: "Karthik7939/Mindstride-test-repo-v1" }]);
        setSelectedRepo("Karthik7939/Mindstride-test-repo-v1");
      });
  }, []);

  // Whenever the selected repository changes, load both the standard
  // documentation suite and the per-file, on-demand docs generated from the
  // /file-docs page, so the user can pick exactly which ones to publish or
  // export. Also (re)load that repo's PDF export history.
  useEffect(() => {
    if (!selectedRepo) {
      setStandardDocs([]);
      setFileDocs([]);
      setSelectedFiles(new Set());
      setExportHistory([]);
      return;
    }

    const repoSlug = selectedRepo.replace("/", "_");
    setDocsLoading(true);

    Promise.all([
      fetch(`${BACKEND_BASE}/api/documents`)
        .then((res) => (res.ok ? res.json() : []))
        .then((docs: StandardDocSummary[]) =>
          Array.isArray(docs)
            ? docs
                .filter((d) => d.repo_id === repoSlug)
                .map((d) => ({
                  key: `standard:${d.source_path}`,
                  filename: d.source_path.slice(d.repo_id.length + 1),
                  label: d.source_path.slice(d.repo_id.length + 1),
                  sublabel: "Standard documentation suite",
                  kind: "standard" as const,
                }))
            : []
        )
        .catch(() => [] as PublishableDoc[]),
      fetch(`${BACKEND_BASE}/api/files/docs/${encodeURIComponent(selectedRepo)}`)
        .then((res) => (res.ok ? res.json() : []))
        .then((docs: FileDocSummary[]) =>
          Array.isArray(docs)
            ? docs.map((d) => ({
                key: `file:${d.source_path}`,
                filename: `${d.source_path}.md`,
                label: d.source_path,
                sublabel: "File-specific documentation",
                kind: "file" as const,
              }))
            : []
        )
        .catch(() => [] as PublishableDoc[]),
    ]).then(([standard, files]) => {
      setStandardDocs(standard);
      setFileDocs(files);
      // Default: the standard suite pre-selected (matches the previous
      // "Publish All Docs" behaviour); file-specific docs are opt-in.
      setSelectedFiles(new Set(standard.map((d) => d.filename)));
      setDocsLoading(false);
    });

    setHistoryLoading(true);
    fetch(`${BACKEND_BASE}/api/export/history?repository_name=${encodeURIComponent(selectedRepo)}`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setExportHistory(Array.isArray(data) ? data : []))
      .catch(() => setExportHistory([]))
      .finally(() => setHistoryLoading(false));
  }, [selectedRepo]);

  const toggleFile = (filename: string) => {
    setSelectedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  };

  const selectAllDocs = () => {
    setSelectedFiles(new Set([...standardDocs, ...fileDocs].map((d) => d.filename)));
  };

  const clearAllDocs = () => setSelectedFiles(new Set());

  const handleSaveToken = () => {
    localStorage.setItem("docubear_gitbook_token", apiToken);
    localStorage.setItem("docubear_gitbook_space_id", spaceId);
    localStorage.setItem("docubear_gitbook_public_url", publicBaseUrl);
  };

  const handleTestConnection = async () => {
    if (!spaceId.trim()) {
      setConnectionStatus({ success: false, message: "Please enter a GitBook Space ID." });
      return;
    }

    setTestingConnection(true);
    setConnectionStatus(null);
    handleSaveToken();

    try {
      const res = await fetch(`${BACKEND_BASE}/api/gitbook/test-connection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          space_id: spaceId.trim(),
          api_token: apiToken.trim(),
        }),
      });

      const data = await res.json();
      setConnectionStatus({
        success: data.success,
        message: data.message || (data.success ? "Connection successful!" : "Failed to connect."),
      });
    } catch (err: any) {
      setConnectionStatus({
        success: false,
        message: `Network error connecting to backend: ${err.message}`,
      });
    } finally {
      setTestingConnection(false);
    }
  };

  const handlePublishSelected = async () => {
    if (!selectedRepo) {
      alert("Please select a repository.");
      return;
    }
    if (!spaceId.trim()) {
      alert("Please enter a GitBook Space ID.");
      return;
    }
    if (selectedFiles.size === 0) {
      alert("Please select at least one document to publish.");
      return;
    }

    setPublishing(true);
    setPublishResult(null);
    handleSaveToken();

    try {
      const res = await fetch(`${BACKEND_BASE}/api/gitbook/publish-repo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repository_name: selectedRepo,
          space_id: spaceId.trim(),
          api_token: apiToken.trim(),
          public_base_url: publicBaseUrl.trim(),
          files: Array.from(selectedFiles),
        }),
      });

      const data = await res.json();
      setPublishResult(data);
    } catch (err: any) {
      setPublishResult({
        success: false,
        message: `Publish failed: ${err.message}`,
      });
    } finally {
      setPublishing(false);
    }
  };

  const handleGenerateExport = async () => {
    if (!selectedRepo) {
      alert("Please select a repository.");
      return;
    }
    if (selectedFiles.size === 0) {
      alert("Please select at least one document to export.");
      return;
    }

    setExporting(true);
    setExportError(null);

    try {
      const res = await fetch(`${BACKEND_BASE}/api/export/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repository_name: selectedRepo,
          files: Array.from(selectedFiles),
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || "PDF export failed.");
      }
      setExportHistory((prev) => [data as ExportRecord, ...prev]);
    } catch (err: any) {
      setExportError(err.message || "PDF export failed.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <AnimatedContainer className="space-y-8 pb-16">
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column: repository/document selection (2/3 width) -- wider
            so the checklist and history rows have room to breathe. */}
        <div className="space-y-6 lg:col-span-2">
          {/* Repository & Document Selection -- shared by both actions on the right */}
          <AnimatedItem y={15}>
            <div className="rounded-2xl border border-border/80 bg-surface p-6 shadow-md shadow-amber-900/5 space-y-5">
              <div className="space-y-2">
                <label htmlFor="select-repo" className="block text-xs font-bold text-text">
                  Repository
                </label>
                <select
                  id="select-repo"
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="w-full rounded-xl border border-border bg-white px-3.5 py-2.5 text-xs font-bold text-text transition-all focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                >
                  {repos.map((r) => (
                    <option key={r.id} value={r.fullName}>
                      📦 {r.fullName}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-bold text-text">Choose documents</label>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={selectAllDocs} className="text-[11px] font-bold text-accent hover:underline">
                      Select all
                    </button>
                    <span className="text-[11px] text-muted">·</span>
                    <button type="button" onClick={clearAllDocs} className="text-[11px] font-bold text-muted hover:underline">
                      Clear
                    </button>
                  </div>
                </div>

                <div className="max-h-[28rem] overflow-y-auto rounded-xl border border-border bg-white divide-y divide-border/60">
                  {docsLoading ? (
                    <p className="p-4 text-center text-xs text-muted">Loading documents...</p>
                  ) : standardDocs.length === 0 && fileDocs.length === 0 ? (
                    <p className="p-4 text-center text-xs text-muted">
                      No generated documentation found for this repository yet.
                    </p>
                  ) : (
                    <>
                      {standardDocs.length > 0 && (
                        <div className="p-2">
                          <p className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted">
                            Standard Documentation Suite
                          </p>
                          <div className="sm:grid sm:grid-cols-2 sm:gap-x-2">
                            {standardDocs.map((d) => (
                              <label
                                key={d.key}
                                className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-xs font-semibold text-text hover:bg-canvas cursor-pointer"
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedFiles.has(d.filename)}
                                  onChange={() => toggleFile(d.filename)}
                                  className="h-3.5 w-3.5 rounded border-border text-accent focus:ring-accent/30"
                                />
                                {d.label}
                              </label>
                            ))}
                          </div>
                        </div>
                      )}

                      {fileDocs.length > 0 && (
                        <div className="p-2">
                          <p className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted">
                            File-Specific Documentation ({fileDocs.length})
                          </p>
                          <div className="sm:grid sm:grid-cols-2 sm:gap-x-2">
                            {fileDocs.map((d) => (
                              <label
                                key={d.key}
                                className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-xs font-mono text-text hover:bg-canvas cursor-pointer"
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedFiles.has(d.filename)}
                                  onChange={() => toggleFile(d.filename)}
                                  className="h-3.5 w-3.5 rounded border-border text-accent focus:ring-accent/30"
                                />
                                <span className="truncate">{d.label}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
                <p className="text-[11px] text-muted">
                  {selectedFiles.size} document{selectedFiles.size === 1 ? "" : "s"} selected — used for both actions on the right.
                </p>
              </div>
            </div>
          </AnimatedItem>

          {/* Export History */}
          <AnimatedItem y={20}>
            <div className="rounded-2xl border border-border/80 bg-surface p-6 shadow-md shadow-amber-900/5 space-y-4">
              <div className="flex items-center justify-between border-b border-border/60 pb-4">
                <h2 className="text-base font-bold text-text flex items-center gap-2">
                  <svg className="w-5 h-5 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Export History
                </h2>
                <span className="text-xs font-semibold text-muted">{exportHistory.length} PDF{exportHistory.length === 1 ? "" : "s"}</span>
              </div>

              {historyLoading ? (
                <p className="p-4 text-center text-xs text-muted">Loading history...</p>
              ) : exportHistory.length === 0 ? (
                <p className="p-4 text-center text-xs text-muted">
                  No PDFs exported yet for this repository — generate one on the right and it&apos;ll show up here.
                </p>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {exportHistory.map((record) => (
                    <div
                      key={record.id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-border bg-white px-3.5 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-text truncate">{record.download_filename}</p>
                        <p className="text-[11px] text-muted">
                          {formatDate(record.created_at)} · {record.documents.length} doc{record.documents.length === 1 ? "" : "s"} · {formatBytes(record.size_bytes)}
                        </p>
                      </div>
                      <a
                        href={downloadUrlFor(record)}
                        download={record.download_filename}
                        className="shrink-0 inline-flex items-center gap-1 rounded-full border border-border text-text text-[11px] font-bold px-3 py-1.5 hover:border-teal/50 hover:text-teal transition-colors"
                      >
                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-8-4V4m0 8l-4-4m4 4l4-4" />
                        </svg>
                        Download
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </AnimatedItem>
        </div>

        {/* Right column: the two actions (1/3 width) -- forms and a single
            button read fine at this width, and it keeps both actions
            visible together without scrolling past the wide checklist. */}
        <div className="space-y-6">
      {/* Publish to GitBook */}
      <AnimatedItem y={20}>
        <div className="rounded-2xl border border-border/80 bg-surface p-6 shadow-md shadow-amber-900/5 space-y-5">
          <div className="flex items-center justify-between border-b border-border/60 pb-4">
            <h2 className="text-base font-bold text-text flex items-center gap-2">
              <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              Publish to GitBook
            </h2>
            <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 border border-emerald-300 px-2 py-0.5 rounded-full">
              {selectedFiles.size} selected
            </span>
          </div>

          {/* API Token Input */}
          <div className="space-y-2">
            <label htmlFor="gitbook-token" className="block text-xs font-bold text-text">
              GitBook Developer API Token (Optional if set in .env)
            </label>
            <div className="relative">
              <input
                id="gitbook-token"
                type={showToken ? "text" : "password"}
                placeholder="gb_api_token_..."
                value={apiToken}
                onChange={(e) => setApiToken(e.target.value)}
                className="w-full rounded-xl border border-border bg-white px-3.5 py-2.5 pr-10 text-xs font-mono text-text transition-all focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted hover:text-text"
              >
                {showToken ? "Hide" : "Show"}
              </button>
            </div>
            <p className="text-[11px] text-muted">
              Create a token at <strong>GitBook Account Settings → Developer → API Tokens</strong>.
            </p>
          </div>

          {/* Space ID Input */}
          <div className="space-y-2">
            <label htmlFor="gitbook-space-id" className="block text-xs font-bold text-text">
              GitBook Space URL <span className="text-rose-600">*</span>
            </label>
            <input
              id="gitbook-space-id"
              type="text"
              placeholder="https://app.gitbook.com/o/ORG_ID/s/SPACE_ID/"
              value={spaceId}
              onChange={(e) => setSpaceId(e.target.value)}
              className="w-full rounded-xl border border-border bg-white px-3.5 py-2.5 text-xs font-mono text-text transition-all focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
            <p className="text-[11px] text-muted">
              Paste your <strong>full GitBook space URL</strong> from your browser address bar — both the org and space IDs are extracted automatically.
            </p>
          </div>

          {/* Public Server URL */}
          <div className="space-y-2">
            <label htmlFor="gitbook-public-url" className="block text-xs font-bold text-text">
              Public Server URL <span className="text-rose-600">*</span>
            </label>
            <input
              id="gitbook-public-url"
              type="text"
              placeholder="https://abc123.ngrok-free.app"
              value={publicBaseUrl}
              onChange={(e) => setPublicBaseUrl(e.target.value)}
              className="w-full rounded-xl border border-border bg-white px-3.5 py-2.5 text-xs font-mono text-text transition-all focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
            <p className="text-[11px] text-muted">
              Your publicly accessible backend URL (e.g. your <strong>ngrok URL</strong>) — GitBook fetches your docs from this address.
            </p>
          </div>

          {/* Test Connection Button */}
          <div className="flex items-center justify-between pt-1">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testingConnection}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-white px-4 py-2 text-xs font-bold text-text shadow-2xs transition-all hover:bg-accent-soft hover:border-accent/40 hover:text-accent disabled:opacity-50"
            >
              {testingConnection ? "Connecting..." : "Test Space Connection"}
            </button>

            {connectionStatus && (
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
                  connectionStatus.success
                    ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                    : "bg-rose-100 text-rose-800 border border-rose-300"
                }`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    connectionStatus.success ? "bg-emerald-500 animate-pulse" : "bg-rose-500"
                  }`}
                />
                {connectionStatus.message}
              </span>
            )}
          </div>

          {/* Publish Action Button */}
          <div className="pt-2 border-t border-border/60">
            <button
              type="button"
              onClick={handlePublishSelected}
              disabled={publishing || selectedFiles.size === 0}
              className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-5 py-3 text-xs font-bold text-white shadow-md shadow-accent/20 transition-all hover:bg-accent/90 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
            >
              {publishing ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Publishing to GitBook...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  Publish {selectedFiles.size} Selected Document{selectedFiles.size === 1 ? "" : "s"}
                </>
              )}
            </button>
          </div>

          {/* Publishing Results & Status Log */}
          {publishResult && (
            <div className="rounded-xl border border-border/80 bg-white p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className={`text-xs font-bold ${publishResult.success ? "text-emerald-700" : "text-rose-700"}`}>
                  {publishResult.message}
                </span>
                <span className="text-[10px] font-mono text-muted">
                  {publishResult.published_count || 0} / {publishResult.total_files || 4} files
                </span>
              </div>

              {publishResult.results && Array.isArray(publishResult.results) && (
                <div className="space-y-1.5 pt-2 border-t border-border/60">
                  {publishResult.results.map((item: any, idx: number) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-xs p-2 rounded-lg bg-surface/60 border border-border/40"
                    >
                      <span className="font-mono font-semibold text-text">{item.filename}</span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                          item.success
                            ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                            : "bg-rose-100 text-rose-800 border border-rose-300"
                        }`}
                      >
                        {item.success ? "Published" : "Failed"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </AnimatedItem>

      {/* Export to PDF */}
      <AnimatedItem y={20}>
        <div className="rounded-2xl border border-border/80 bg-surface p-6 shadow-md shadow-amber-900/5 space-y-5">
          <div className="flex items-center justify-between border-b border-border/60 pb-4">
            <h2 className="text-base font-bold text-text flex items-center gap-2">
              <svg className="w-5 h-5 text-teal" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Export to PDF
            </h2>
            <span className="text-xs font-semibold text-teal bg-teal/10 border border-teal/30 px-2 py-0.5 rounded-full">
              {selectedFiles.size} selected
            </span>
          </div>

          <p className="text-[11px] text-muted">
            Bundles the documents selected above into one formatted PDF — cover page, table of contents, and page numbers included — rendered entirely offline and ready to download.
          </p>

          <button
            type="button"
            onClick={handleGenerateExport}
            disabled={exporting || selectedFiles.size === 0}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-teal px-5 py-3 text-xs font-bold text-white shadow-md shadow-teal/20 transition-all hover:bg-teal/90 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
          >
            {exporting ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Generating PDF...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2-9.5V7a2 2 0 002 2h3.5M8 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9.5L14 3H8z" />
                </svg>
                Export {selectedFiles.size} Document{selectedFiles.size === 1 ? "" : "s"} as PDF
              </>
            )}
          </button>

          {exportError && (
            <p className="text-xs font-bold text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-3 py-2">
              {exportError}
            </p>
          )}

          {exportHistory.length > 0 && !exportError && (
            <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-bold text-emerald-800">PDF ready — {exportHistory[0].download_filename}</p>
                <p className="text-[11px] text-emerald-700">
                  {exportHistory[0].documents.length} document{exportHistory[0].documents.length === 1 ? "" : "s"} · {formatBytes(exportHistory[0].size_bytes)}
                </p>
              </div>
              <a
                href={downloadUrlFor(exportHistory[0])}
                download={exportHistory[0].download_filename}
                className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold px-3.5 py-2 hover:bg-emerald-500 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-8-4V4m0 8l-4-4m4 4l4-4" />
                </svg>
                Download
              </a>
            </div>
          )}
        </div>
      </AnimatedItem>
        </div>
      </div>
    </AnimatedContainer>
  );
}
