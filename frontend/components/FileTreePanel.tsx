"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";

export interface FileTreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  children?: FileTreeNode[];
  documentable?: boolean;
}

interface FileTreePanelProps {
  tree: FileTreeNode | null;
  loading: boolean;
  error: string | null;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  documentedPaths?: Set<string>;
}

// Paths whose ancestor directories should be expanded by default so a
// freshly loaded tree isn't a single collapsed root node.
const DEFAULT_EXPAND_DEPTH = 1;

function FolderIcon({ open }: { open: boolean }) {
  return open ? (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-7.586a1 1 0 01-.707-.293L9.293 5.293A1 1 0 008.586 5H5a2 2 0 00-2 2z" />
    </svg>
  ) : (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 7a2 2 0 012-2h4.586a1 1 0 01.707.293l1.414 1.414a1 1 0 00.707.293H19a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
    </svg>
  );
}

function FileIcon({ dimmed }: { dimmed: boolean }) {
  return (
    <svg
      className={`w-4 h-4 ${dimmed ? "opacity-40" : ""}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function matchesQuery(node: FileTreeNode, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  if (node.name.toLowerCase().includes(q)) return true;
  if (node.type === "dir" && node.children) {
    return node.children.some((c) => matchesQuery(c, query));
  }
  return false;
}

function TreeNodeView({
  node,
  depth,
  query,
  selectedPath,
  onSelectFile,
  documentedPaths,
}: {
  node: FileTreeNode;
  depth: number;
  query: string;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  documentedPaths?: Set<string>;
}) {
  const [expanded, setExpanded] = useState(depth < DEFAULT_EXPAND_DEPTH);

  // Auto-expand directories that contain a search match so results are visible.
  useEffect(() => {
    if (query && node.type === "dir") setExpanded(true);
  }, [query, node.type]);

  if (!matchesQuery(node, query)) return null;

  const indent = { paddingLeft: `${0.5 + depth * 1}rem` };

  if (node.type === "dir") {
    const children = node.children ?? [];
    return (
      <div>
        <button
          onClick={() => setExpanded((e) => !e)}
          style={indent}
          className="flex w-full items-center gap-2 rounded-lg py-1.5 pr-2 text-left text-xs font-semibold text-text hover:bg-canvas transition-colors"
        >
          <svg
            className={`w-3 h-3 flex-shrink-0 text-muted transition-transform ${expanded ? "rotate-90" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-teal flex-shrink-0">
            <FolderIcon open={expanded} />
          </span>
          <span className="truncate">{node.name}</span>
        </button>
        {expanded && children.length > 0 && (
          <div>
            {children.map((child) => (
              <TreeNodeView
                key={child.path}
                node={child}
                depth={depth + 1}
                query={query}
                selectedPath={selectedPath}
                onSelectFile={onSelectFile}
                documentedPaths={documentedPaths}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const isDocumentable = node.documentable !== false;
  const isActive = selectedPath === node.path;
  const isDocumented = documentedPaths?.has(node.path) ?? false;

  return (
    <button
      onClick={() => isDocumentable && onSelectFile(node.path)}
      disabled={!isDocumentable}
      style={indent}
      title={
        isDocumentable
          ? isDocumented
            ? `${node.path} (documented)`
            : node.path
          : `${node.path} (not documentable)`
      }
      className={`relative flex w-full items-center gap-2 rounded-lg py-1.5 pr-2 text-left text-xs transition-colors ${
        isActive
          ? "bg-teal/10 text-teal font-bold"
          : isDocumentable
            ? "text-text/85 hover:bg-canvas hover:text-text"
            : "text-muted/50 cursor-not-allowed"
      }`}
    >
      {isActive && (
        <motion.span
          layoutId="file-tree-active-pill"
          className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-r-full bg-teal"
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        />
      )}
      <span className="relative flex-shrink-0">
        <FileIcon dimmed={!isDocumentable} />
        {isDocumented && (
          <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-teal ring-1 ring-surface" />
        )}
      </span>
      <span className="truncate">{node.name}</span>
    </button>
  );
}

export default function FileTreePanel({
  tree,
  loading,
  error,
  selectedPath,
  onSelectFile,
  documentedPaths,
}: FileTreePanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [query, setQuery] = useState("");

  const rootChildren = useMemo(() => tree?.children ?? [], [tree]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className={`group relative flex flex-col h-[calc(100vh-7.5rem)] overflow-hidden rounded-2xl border border-border bg-surface shadow-sm transition-all duration-300 ${
        isCollapsed ? "w-[4.5rem]" : "w-[20rem]"
      }`}
    >
      <div className="h-1.5 w-full flex-shrink-0 bg-presidio-gradient" />

      <div className={`border-b border-border flex-shrink-0 transition-all ${isCollapsed ? "p-3 flex flex-col items-center" : "p-4.5"}`}>
        <div className={`flex items-center ${isCollapsed ? "flex-col gap-3" : "justify-between gap-2"}`}>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-border bg-canvas text-teal shadow-2xs">
              <FolderIcon open={false} />
            </div>
            {!isCollapsed && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">REPOSITORY</p>
                <h2 className="text-sm font-bold text-text">File Explorer</h2>
              </div>
            )}
          </div>

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

        {!isCollapsed && (
          <div className="mt-3.5">
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-muted">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <input
                type="text"
                placeholder="Filter files..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full rounded-full border border-border bg-canvas py-2 pl-9 pr-8 text-xs font-medium text-text placeholder:text-muted/60 transition-all focus:border-teal focus:bg-surface focus:outline-none focus:ring-2 focus:ring-teal/20"
              />
            </div>
          </div>
        )}
      </div>

      {!isCollapsed && (
        <div className="flex-1 overflow-y-auto p-2.5 bg-canvas/40">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-xs text-muted">Loading file tree...</div>
          ) : error ? (
            <div className="p-4 text-center">
              <p className="text-xs font-bold text-text">Couldn't load files</p>
              <p className="mt-1 text-[11px] text-muted">{error}</p>
            </div>
          ) : rootChildren.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center px-4">
              <p className="text-xs font-bold text-text">Select a repository</p>
              <p className="mt-1 text-[11px] text-muted">Its file tree will appear here.</p>
            </div>
          ) : (
            rootChildren.map((child) => (
              <TreeNodeView
                key={child.path}
                node={child}
                depth={0}
                query={query}
                selectedPath={selectedPath}
                onSelectFile={onSelectFile}
                documentedPaths={documentedPaths}
              />
            ))
          )}
        </div>
      )}
    </motion.div>
  );
}
