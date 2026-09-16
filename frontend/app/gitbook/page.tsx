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

interface FileDocSummary {
  id: string;
  repoId: string;
  title: string;
  sourcePath: string;
}

/** One selectable row in the "choose files to publish" list. */
interface PublishableDoc {
  key: string;
  /** Path relative to generated_docs/<repo_slug>/, as expected by /api/gitbook/publish-repo. */
  filename: string;
  label: string;
  sublabel: string;
  kind: "standard" | "file";
}

export default function GitBookPage() {
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
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());

  // Load saved settings from localStorage and fetch connected repos
  useEffect(() => {
    const savedToken = localStorage.getItem("docubear_gitbook_token") || "";
    const savedSpaceId = localStorage.getItem("docubear_gitbook_space_id") || "";
    const savedPublicUrl = localStorage.getItem("docubear_gitbook_public_url") || "";
    setApiToken(savedToken);
    setSpaceId(savedSpaceId);
    setPublicBaseUrl(savedPublicUrl);

    // Fetch repos
    fetch("http://127.0.0.1:8000/api/documents/repos")
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
  // /file-docs page, so the user can pick exactly which ones to publish.
  useEffect(() => {
    if (!selectedRepo) {
      setStandardDocs([]);
      setFileDocs([]);
      setSelectedFiles(new Set());
      return;
    }

    const repoSlug = selectedRepo.replace("/", "_");
    setDocsLoading(true);

    Promise.all([
      fetch("http://127.0.0.1:8000/api/documents")
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
      fetch(`http://127.0.0.1:8000/api/files/docs/${encodeURIComponent(selectedRepo)}`)
        .then((res) => (res.ok ? res.json() : []))
        .then((docs: FileDocSummary[]) =>
          Array.isArray(docs)
            ? docs.map((d) => ({
                key: `file:${d.sourcePath}`,
                filename: `${d.sourcePath}.md`,
                label: d.sourcePath,
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
      const res = await fetch("http://127.0.0.1:8000/api/gitbook/test-connection", {
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
      const res = await fetch("http://127.0.0.1:8000/api/gitbook/publish-repo", {
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

  return (
    <AnimatedContainer className="space-y-8 pb-16">
      {/* Header Banner */}
      <AnimatedItem y={15}>
        <div className="relative overflow-hidden rounded-3xl border border-blue-500/20 bg-gradient-to-br from-surface via-blue-500/5 to-canvas p-6 sm:p-8 shadow-xl shadow-blue-900/5">
          <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-blue-500/10 blur-3xl" />
          
          <div className="relative z-10 space-y-3 max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-300 bg-blue-100/90 px-3 py-1 text-xs font-bold text-blue-800 shadow-2xs">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              Direct Integration Module
            </div>

            <h1 className="text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
              GitBook Publishing Hub
            </h1>
            <p className="text-sm font-medium text-muted leading-relaxed">
              Connect DocuBear directly to your GitBook Spaces. Choose exactly which documents to publish — the standard project suite (<code className="text-teal font-bold">README.md</code>, <code className="text-purple-700 font-bold">ARCHITECTURE.md</code>, <code className="text-emerald-700 font-bold">CHANGELOG.md</code>, <code className="text-rose-700 font-bold">SECURITY.md</code>, and more), individual file-specific docs generated from the File Docs page, or any mix of both.
            </p>
          </div>
        </div>
      </AnimatedItem>

      {/* Main 2-Column Grid */}
      <div className="grid gap-8 lg:grid-cols-3">
        {/* Left Column: API Configuration & Publishing Form (2/3 width) */}
        <div className="space-y-6 lg:col-span-2">
          {/* Credentials Box */}
          <AnimatedItem y={20}>
          <div className="rounded-2xl border border-border/80 bg-surface p-6 shadow-md shadow-amber-900/5 space-y-5">
            <div className="flex items-center justify-between border-b border-border/60 pb-4">
              <h2 className="text-base font-bold text-text flex items-center gap-2">
                <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
                GitBook Credentials & Credentials
              </h2>
              <span className="text-xs font-semibold text-muted">REST API v1</span>
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
                Paste your <strong>full GitBook space URL</strong> — the one from your browser address bar (e.g. <code>app.gitbook.com/o/<strong>ORG_ID</strong>/s/<strong>SPACE_ID</strong>/</code>). Both IDs are extracted automatically.
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
                Your publicly accessible backend URL (e.g. your <strong>ngrok URL</strong>). GitBook fetches your docs from this address. Copy it from your <code>ngrok</code> terminal output.
              </p>
            </div>

            {/* Test Connection Button */}
            <div className="flex items-center justify-between pt-2">
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
          </div>

          {/* Repository Publishing Box */}
          <div className="rounded-2xl border border-border/80 bg-surface p-6 shadow-md shadow-amber-900/5 space-y-5">
            <div className="flex items-center justify-between border-b border-border/60 pb-4">
              <h2 className="text-base font-bold text-text flex items-center gap-2">
                <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 0115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                Publish to GitBook
              </h2>
              <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 border border-emerald-300 px-2 py-0.5 rounded-full">
                {selectedFiles.size} selected
              </span>
            </div>

            {/* Select Repository */}
            <div className="space-y-2">
              <label htmlFor="select-repo" className="block text-xs font-bold text-text">
                Select Project Repository
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

            {/* Document Selection */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-bold text-text">
                  Choose documents to publish
                </label>
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

              <div className="max-h-72 overflow-y-auto rounded-xl border border-border bg-white divide-y divide-border/60">
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
                    )}

                    {fileDocs.length > 0 && (
                      <div className="p-2">
                        <p className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted">
                          File-Specific Documentation ({fileDocs.length})
                        </p>
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
                    )}
                  </>
                )}
              </div>
            </div>

            {/* Publish Action Button */}
            <div className="pt-2">
              <button
                type="button"
                onClick={handlePublishSelected}
                disabled={publishing || selectedFiles.size === 0}
                className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-5 py-3 text-xs font-bold text-white shadow-md shadow-accent/20 transition-all hover:bg-accent/90 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
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
              <div className="mt-4 rounded-xl border border-border/80 bg-white p-4 space-y-3">
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
      </div>

        {/* Right Column: Setup Guide & Space Info (1/3 width) */}
        <div className="space-y-6">
          <AnimatedItem y={25}>
            <div className="rounded-2xl border border-border/80 bg-surface p-5 shadow-sm space-y-4">
              <h3 className="text-sm font-bold text-text flex items-center gap-2 border-b border-border/60 pb-3">
                <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                GitBook Setup Instructions
              </h3>

              <div className="space-y-3 text-xs text-muted leading-relaxed">
                <div className="space-y-1">
                  <p className="font-bold text-text">1. Create a Developer API Token</p>
                  <p>
                    Log into GitBook, go to <strong>Account Settings → Developer → API Tokens</strong>, and create a personal API token.
                  </p>
                </div>

                <div className="space-y-1">
                  <p className="font-bold text-text">2. Locate Your Space ID</p>
                  <p>
                    Open your target GitBook space in your browser. The Space ID is located in the browser URL path (e.g. <code>app.gitbook.com/s/<strong>space_12345</strong></code>).
                  </p>
                </div>

                <div className="space-y-1">
                  <p className="font-bold text-text">3. One-Click Publishing</p>
                  <p>
                    DocuBear automatically translates and formats all standard documents for clean rendering inside GitBook.
                  </p>
                </div>
              </div>
            </div>
          </AnimatedItem>
        </div>
      </div>
    </AnimatedContainer>
  );
}
