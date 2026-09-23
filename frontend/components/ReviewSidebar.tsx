"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { DocVersion } from "@/types";
import { motion } from "framer-motion";

// This sidebar lives in the /review layout, which refetches its document
// list on every doc navigation — that re-render resets plain component
// state, so the repo filter would silently snap back to "All Repositories"
// every time you clicked into a different .md file. Persist it instead.
const REPO_FILTER_STORAGE_KEY = "docubear_repo_filter";

export default function ReviewSidebar({ documents }: { documents: DocVersion[] }) {
  const pathname = usePathname();
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [selectedRepo, setSelectedRepo] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const repos = useMemo(() => {
    const repoSet = new Set(documents.map((doc) => doc.repoId));
    return Array.from(repoSet).filter(Boolean);
  }, [documents]);

  // Restore the last-selected repo filter on mount — but only if that repo
  // still exists in the current document list (it may have been removed).
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(REPO_FILTER_STORAGE_KEY);
      if (saved && (saved === "all" || repos.includes(saved))) {
        setSelectedRepo(saved);
      }
    } catch {
      // Storage unavailable — filter just won't survive navigation.
    }
  }, [repos]);

  function handleRepoChange(value: string) {
    setSelectedRepo(value);
    try {
      window.localStorage.setItem(REPO_FILTER_STORAGE_KEY, value);
    } catch {
      // Storage unavailable — filter just won't survive navigation.
    }
  }

  const filteredDocs = useMemo(() => {
    return documents.filter((doc) => {
      const matchesRepo = selectedRepo === "all" || doc.repoId === selectedRepo;
      const matchesSearch =
        !searchQuery.trim() ||
        doc.title.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesRepo && matchesSearch;
    });
  }, [documents, selectedRepo, searchQuery]);

  // Group documents by repo for clean organization
  const groupedDocs = useMemo(() => {
    const map: Record<string, DocVersion[]> = {};
    filteredDocs.forEach((doc) => {
      const key = doc.repoId || "Default Repository";
      if (!map[key]) map[key] = [];
      map[key].push(doc);
    });
    return map;
  }, [filteredDocs]);

  const updatedCount = filteredDocs.filter((d) => d.hasChanges).length;

  const getDocTypeInfo = (title: string) => {
    const filename = title.split("/").at(-1)?.toUpperCase() || "";
    if (filename.includes("README")) {
      return {
        label: "README",
        bg: "bg-teal/10 text-teal border-teal/20",
        icon: (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      };
    }
    if (filename.includes("ARCHITECTURE")) {
      return {
        label: "Architecture",
        bg: "bg-text/5 text-text border-border",
        icon: (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        ),
      };
    }
    if (filename.includes("REQUIREMENT")) {
      return {
        label: "Requirements",
        bg: "bg-indigo-50 text-indigo-600 border-indigo-200",
        icon: (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
        ),
      };
    }
    if (filename.includes("WORKFLOW")) {
      return {
        label: "Workflow",
        bg: "bg-amber-50 text-amber-600 border-amber-200",
        icon: (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        ),
      };
    }
    if (filename.includes("REPORTS")) {
      return {
        label: "Reports",
        bg: "bg-purple-50 text-purple-600 border-purple-200",
        icon: (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
      };
    }
    if (filename.includes("CHANGELOG")) {
      return {
        label: "Changelog",
        bg: "bg-teal/10 text-teal border-teal/20",
        icon: (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      };
    }
    if (filename.includes("SECURITY")) {
      return {
        label: "Security",
        bg: "bg-text/5 text-text border-border",
        icon: (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      };
    }
    return {
      label: "Document",
      bg: "bg-text/5 text-text border-border",
      icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    };
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className={`group relative flex flex-col h-[calc(100vh-7.5rem)] overflow-hidden rounded-2xl border border-border bg-surface shadow-sm transition-all duration-300 ${
        isCollapsed ? "w-[4.5rem]" : "w-[22rem]"
      }`}
    >
      {/* Top Presidio gradient bar */}
      <div className="h-1.5 w-full flex-shrink-0 bg-presidio-gradient" />

      {/* Header section */}
      <div className={`border-b border-border flex-shrink-0 transition-all ${isCollapsed ? "p-3 flex flex-col items-center" : "p-4.5"}`}>
        <div className={`flex items-center ${isCollapsed ? "flex-col gap-3" : "justify-between gap-2"}`}>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-border bg-canvas text-teal shadow-2xs">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            {!isCollapsed && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">DOCUMENT SUITE</p>
                <h2 className="text-sm font-bold text-text">
                  {filteredDocs.length} Document{filteredDocs.length !== 1 ? "s" : ""}
                </h2>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {!isCollapsed && updatedCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-yellow-300 bg-yellow-50 px-2.5 py-0.5 text-[10px] font-bold text-yellow-800">
                <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse" />
                {updatedCount} Updated
              </span>
            )}
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-canvas text-muted hover:text-text hover:border-text/40 transition-all"
              title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              <svg
                className={`w-3.5 h-3.5 transition-transform duration-300 ${isCollapsed ? "rotate-180" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>
          </div>
        </div>

        {!isCollapsed && (
          <div className="mt-3.5 space-y-2.5">
            {/* Search input with rounded-full pill shape */}
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-muted">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <input
                type="text"
                placeholder="Filter documents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-full border border-border bg-canvas py-2 pl-9 pr-8 text-xs font-medium text-text placeholder:text-muted/60 transition-all focus:border-teal focus:bg-surface focus:outline-none focus:ring-2 focus:ring-teal/20"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted hover:text-text"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>

            {/* Repo filter dropdown */}
            {repos.length > 1 && (
              <select
                id="repo-filter"
                value={selectedRepo}
                onChange={(e) => handleRepoChange(e.target.value)}
                className="w-full rounded-full border border-border bg-canvas px-3.5 py-1.5 text-xs font-semibold text-text transition-all focus:border-teal focus:bg-surface focus:outline-none focus:ring-2 focus:ring-teal/20"
              >
                <option value="all">All Repositories ({documents.length})</option>
                {repos.map((repo) => (
                  <option key={repo} value={repo}>{repo}</option>
                ))}
              </select>
            )}
          </div>
        )}
      </div>

      {/* Document List grouped by Repository */}
      <div className={`flex-1 overflow-y-auto ${isCollapsed ? "p-2 space-y-3 flex flex-col items-center" : "p-3 space-y-4 bg-canvas/40"}`}>
        {filteredDocs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full p-6 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-teal/10 text-teal mb-2.5">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            {!isCollapsed && (
              <>
                <p className="text-xs font-bold text-text">No matching documents</p>
                <p className="mt-1 text-[11px] text-muted">Try clearing your search query.</p>
              </>
            )}
          </div>
        ) : (
          Object.entries(groupedDocs).map(([repoName, docs]) => (
            <div key={repoName} className="space-y-2 w-full">
              {!isCollapsed && Object.keys(groupedDocs).length > 1 && (
                <div className="px-2 pt-1 pb-0.5 flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-teal truncate">
                    {repoName}
                  </span>
                  <span className="text-[9px] font-mono text-muted/80">{docs.length}</span>
                </div>
              )}

              <nav className="space-y-1.5 w-full">
                {docs.map((doc) => {
                  const isActive = pathname === `/review/${doc.id}`;
                  const docInfo = getDocTypeInfo(doc.title);
                  const fileName = doc.title.split("/").at(-1) || doc.title;
                  const folderPath = doc.title.split("/").slice(0, -1).join("/") || "root";

                  if (isCollapsed) {
                    return (
                      <Link
                        key={doc.id}
                        href={`/review/${doc.id}`}
                        className={`group relative flex items-center justify-center rounded-xl p-2.5 transition-all duration-200 ${
                          isActive ? "bg-teal/15 ring-2 ring-teal" : "hover:bg-surface"
                        }`}
                        title={`${fileName} (${folderPath})`}
                      >
                        <div className={`flex h-9 w-9 items-center justify-center rounded-xl border ${docInfo.bg}`}>
                          {docInfo.icon}
                        </div>
                        {doc.hasChanges && (
                          <span className="absolute top-1 right-1 h-2.5 w-2.5 rounded-full bg-yellow-400 ring-2 ring-white" />
                        )}
                      </Link>
                    );
                  }

                  return (
                    <Link
                      key={doc.id}
                      href={`/review/${doc.id}`}
                      className={`group relative flex items-center gap-3.5 rounded-xl p-3 text-xs transition-all duration-200 ${
                        isActive
                          ? "bg-teal/10 border-l-4 border-teal text-teal shadow-xs font-bold border-y border-r border-teal/20"
                          : "bg-surface hover:bg-white text-text border border-border/60 hover:border-teal/30 hover:shadow-2xs"
                      }`}
                    >
                      {/* Active side indicator pill */}
                      {isActive && (
                        <motion.span
                          layoutId="active-sidebar-pill"
                          className="absolute left-0 top-2.5 bottom-2.5 w-1 rounded-r-full bg-teal"
                          transition={{ type: "spring", stiffness: 400, damping: 30 }}
                        />
                      )}

                      {/* Icon badge */}
                      <div
                        className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl border transition-colors ${
                          isActive
                            ? "bg-teal text-white border-teal"
                            : `${docInfo.bg}`
                        }`}
                      >
                        {docInfo.icon}
                      </div>

                      {/* Info column */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className={`truncate font-semibold ${isActive ? "text-teal text-[13px] font-bold" : "text-text text-[13px] group-hover:text-teal"}`}>
                            {fileName}
                          </span>
                          {doc.hasChanges && (
                            <span className="flex-shrink-0 inline-flex items-center gap-1 rounded-full bg-yellow-100 border border-yellow-300 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider text-yellow-800">
                              <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse" />
                              New
                            </span>
                          )}
                        </div>

                        <div className="mt-1 flex items-center justify-between text-[11px]">
                          <span className={`truncate font-mono ${isActive ? "text-teal/80 font-medium" : "text-muted opacity-75"}`}>
                            {folderPath}
                          </span>
                          <span className={`font-mono text-[9px] font-bold uppercase tracking-wider ${isActive ? "text-teal" : "text-muted"}`}>
                            {docInfo.label}
                          </span>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </nav>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className={`border-t border-border bg-canvas px-4 py-3 flex items-center justify-between text-xs font-semibold flex-shrink-0 ${isCollapsed ? "flex-col gap-2" : ""}`}>
        {!isCollapsed && (
          <span className="flex items-center gap-2 text-[11px] font-bold text-text">
            <span className="h-2 w-2 rounded-full bg-teal" />
            DocuBear Hub
          </span>
        )}
        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-emerald-800 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          {!isCollapsed && "Live Synced"}
        </span>
      </div>
    </motion.div>
  );
}
