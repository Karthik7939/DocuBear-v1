"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Repo, RequirementsAnalysisResult } from "@/types";

type BootstrapStatus = "idle" | "loading" | "success" | "error" | "no_backend";
type IndexStatus = { indexed: boolean; vector_count: number; backend: string } | null;

function repoPathFromFullName(fullName: string): string {
  return `repositories/${fullName.replace("/", "_")}`;
}

export default function RepoCard({ repo }: { repo: Repo }) {
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatus>("idle");
  const [bootstrapMessage, setBootstrapMessage] = useState<string>("");
  const [indexStatus, setIndexStatus] = useState<IndexStatus>(null);
  const [reqData, setReqData] = useState<RequirementsAnalysisResult | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  const fetchStatus = useCallback(async () => {
    setLoadingStatus(true);
    try {
      const [ragRes, reqRes] = await Promise.allSettled([
        fetch(`/api/rag/status?repo=${encodeURIComponent(repo.fullName)}`, { cache: "no-store" }),
        fetch(`/api/requirements/${encodeURIComponent(repo.fullName)}`, { cache: "no-store" })
      ]);

      if (ragRes.status === "fulfilled" && ragRes.value.ok) {
        const data = await ragRes.value.json();
        setIndexStatus(data);
      } else {
        setIndexStatus(null);
      }

      if (reqRes.status === "fulfilled" && reqRes.value.ok) {
        const reqJson = await reqRes.value.json();
        setReqData(reqJson);
      } else {
        setReqData(null);
      }
    } catch {
      setIndexStatus(null);
      setReqData(null);
    } finally {
      setLoadingStatus(false);
    }
  }, [repo.fullName]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  async function handleBootstrap() {
    setBootstrapStatus("loading");
    setBootstrapMessage("");

    try {
      const res = await fetch("/api/rag/bootstrap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repositoryName: repo.fullName,
          repositoryPath: repoPathFromFullName(repo.fullName),
          commitSha: "HEAD",
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 503) {
          setBootstrapStatus("no_backend");
          setBootstrapMessage("Backend is offline. Start the Python server first.");
        } else {
          setBootstrapStatus("error");
          setBootstrapMessage(data?.error || "Bootstrap failed. Check backend logs.");
        }
      } else {
        setBootstrapStatus("success");
        setBootstrapMessage(
          data?.message || "Embeddings generated and stored successfully."
        );
        setTimeout(() => fetchStatus(), 1500);
      }
    } catch {
      setBootstrapStatus("no_backend");
      setBootstrapMessage("Cannot reach backend. Is it running on port 8000?");
    }
  }

  const indexBadge = loadingStatus ? (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider px-3 py-1 rounded-full bg-canvas text-muted border border-border">
      <span className="w-1.5 h-1.5 rounded-full bg-muted animate-pulse" />
      Checking…
    </span>
  ) : !indexStatus || !indexStatus.indexed ? (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider px-3 py-1 rounded-full bg-canvas text-muted border border-border">
      <span className="w-1.5 h-1.5 rounded-full bg-muted" />
      Not indexed
    </span>
  ) : (
    <span
      className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider px-3 py-1 rounded-full bg-teal/10 text-teal border border-teal/20"
      title={`${indexStatus.vector_count} vectors in Pinecone (${indexStatus.backend})`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-teal" />
      {indexStatus.vector_count > 0
        ? `${indexStatus.vector_count} vectors`
        : "Indexed"}
    </span>
  );

  const bootstrapConfig = {
    idle: { label: "Bootstrap RAG", icon: "★", cls: "bg-accent-cta text-text hover:bg-yellow-300" },
    loading: { label: "Indexing…", icon: null, cls: "bg-accent-cta text-text opacity-70 cursor-not-allowed" },
    success: { label: "Re-index", icon: "✓", cls: "bg-teal text-white hover:bg-teal/90" },
    error: { label: "Retry", icon: "↺", cls: "bg-danger text-white hover:bg-red-700" },
    no_backend: { label: "Retry", icon: "↺", cls: "bg-danger text-white hover:bg-red-700" },
  }[bootstrapStatus];

  return (
    <div className="border border-border rounded-2xl bg-surface overflow-hidden shadow-xs hover:border-teal/40 transition-all">
      {/* Top Presidio gradient bar */}
      <div className="h-1 w-full bg-presidio-gradient" />

      <div className="p-5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-teal mb-0.5">REPOSITORY</p>
          <div className="flex items-center gap-2">
            <p className="text-sm font-bold text-text truncate">{repo.fullName}</p>
          </div>
          <p className="text-xs text-muted mt-1">
            Connected {new Date(repo.connectedAt).toLocaleDateString("en-US")}
          </p>
          {indexStatus?.backend && (
            <p className="text-[11px] text-muted mt-0.5 font-mono">
              Backend: <span className="font-semibold text-text">{indexStatus.backend}</span>
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0 justify-end">
          <span
            className={`text-[11px] px-3 py-1 rounded-full font-semibold uppercase tracking-wider border ${
              repo.webhookActive
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-canvas text-muted border-border"
            }`}
          >
            {repo.webhookActive ? "Webhook active" : "Awaiting webhook"}
          </span>

          {indexBadge}

          {/* Requirements specs status / upload button */}
          {reqData ? (
            (() => {
              const passedCount = (reqData.functionalCount?.completed || 0) + (reqData.nonFunctionalCount?.completed || 0);
              const totalCount = (reqData.functionalCount?.total || 0) + (reqData.nonFunctionalCount?.total || 0) || reqData.items?.length || 0;
              return (
                <Link
                  href={`/requirements?repo=${encodeURIComponent(repo.fullName)}`}
                  className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-3.5 py-2 rounded-full border border-teal/40 bg-teal/10 text-teal hover:bg-teal hover:text-white transition-all shadow-xs active:scale-95"
                  title={`Spec: ${reqData.fileName} • ${passedCount}/${totalCount} Requirements Passed (${reqData.overallScore}% score)`}
                >
                  <span className="text-emerald-700 font-extrabold">✓</span>
                  <span>{passedCount}/{totalCount} Passed</span>
                  <span className="text-[10px] opacity-75">({reqData.overallScore}%) ↗</span>
                </Link>
              );
            })()
          ) : (
            <Link
              href={`/requirements?repo=${encodeURIComponent(repo.fullName)}`}
              className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-3.5 py-2 rounded-full border border-border bg-canvas text-text/80 hover:border-teal/50 hover:bg-teal/5 hover:text-teal transition-all shadow-xs active:scale-95"
            >
              <span>📄</span>
              <span>Upload Specs</span>
            </Link>
          )}

          <button
            id={`bootstrap-btn-${repo.id}`}
            onClick={handleBootstrap}
            disabled={bootstrapStatus === "loading"}
            className={`flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-4 py-2 rounded-full
                       transition-all duration-150 active:scale-95 shadow-xs ${bootstrapConfig.cls}`}
          >
            {bootstrapStatus === "loading" ? (
              <>
                <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                </svg>
                Indexing…
              </>
            ) : (
              <>
                {bootstrapConfig.icon && <span>{bootstrapConfig.icon}</span>}
                {bootstrapConfig.label}
              </>
            )}
          </button>
        </div>
      </div>

      {bootstrapMessage && (
        <div
          className={`px-5 py-2.5 text-xs border-t border-border flex items-start gap-2 ${
            bootstrapStatus === "success"
              ? "bg-emerald-50 text-emerald-700"
              : "bg-red-50 text-danger"
          }`}
        >
          {bootstrapStatus === "success" ? "✓" : "⚠"} {bootstrapMessage}
        </div>
      )}
    </div>
  );
}