"use client";

/**
 * lib/agentContext.tsx
 * -----------------------
 * Lets the single, persistent AgentSidebar (mounted once in app/layout.tsx)
 * know which document the user currently has open, without the sidebar
 * itself living inside -- and therefore unmounting with -- individual pages.
 *
 * Pages call useRegisterOpenDocument() with their current doc info; the
 * most recently registered one wins. The sidebar reads it via
 * useAgentContext().openDocument and reconnects its assistant session
 * scoped to the new document when it changes, without the sidebar panel
 * itself ever unmounting (its open/closed state and conversation persist
 * across navigation).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  ReactNode,
} from "react";

export interface OpenDocumentInfo {
  repositoryName: string;
  documentId?: string;
  documentTitle?: string;
  documentContent?: string;
  onDocumentChanged?: (newContent: string, previousContent: string) => void;
}

interface AgentContextValue {
  openDocument: OpenDocumentInfo | null;
  registerOpenDocument: (doc: OpenDocumentInfo) => void;
  clearOpenDocument: (documentId: string | undefined, repositoryName: string) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
}

const AgentContext = createContext<AgentContextValue | null>(null);

export function AgentProvider({ children }: { children: ReactNode }) {
  const [openDocument, setOpenDocument] = useState<OpenDocumentInfo | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  const registerOpenDocument = useCallback((doc: OpenDocumentInfo) => {
    setOpenDocument(doc);
  }, []);

  // Only clear if the caller is still the registered one -- guards against
  // an outgoing page's unmount cleanup clobbering the incoming page's
  // registration when navigation ordering isn't guaranteed.
  const clearOpenDocument = useCallback((documentId: string | undefined, repositoryName: string) => {
    setOpenDocument((prev) => {
      if (!prev) return prev;
      const isCaller = prev.documentId === documentId && prev.repositoryName === repositoryName;
      return isCaller ? null : prev;
    });
  }, []);

  const value = useMemo<AgentContextValue>(
    () => ({ openDocument, registerOpenDocument, clearOpenDocument, sidebarCollapsed, setSidebarCollapsed }),
    [openDocument, registerOpenDocument, clearOpenDocument, sidebarCollapsed]
  );

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}

export function useAgentContext(): AgentContextValue {
  const ctx = useContext(AgentContext);
  if (!ctx) throw new Error("useAgentContext must be used within an AgentProvider");
  return ctx;
}

/**
 * Pages call this with their current document (or null if none is open) to
 * tell the persistent sidebar what to scope the assistant to. Registers on
 * mount and whenever the document's identity changes; unregisters on
 * unmount so a stale page doesn't keep "owning" the assistant.
 */
export function useRegisterOpenDocument(doc: OpenDocumentInfo | null): void {
  const { registerOpenDocument, clearOpenDocument } = useAgentContext();

  // Keep the callback fresh without making it a dependency that would
  // otherwise force a re-register (and downstream reconnect) on every
  // parent re-render.
  const callbackRef = useRef(doc?.onDocumentChanged);
  callbackRef.current = doc?.onDocumentChanged;

  const repositoryName = doc?.repositoryName;
  const documentId = doc?.documentId;
  const documentTitle = doc?.documentTitle;
  const documentContent = doc?.documentContent;

  useEffect(() => {
    if (!repositoryName) return;
    registerOpenDocument({
      repositoryName,
      documentId,
      documentTitle,
      documentContent,
      onDocumentChanged: (newContent, previousContent) => callbackRef.current?.(newContent, previousContent),
    });
    return () => clearOpenDocument(documentId, repositoryName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repositoryName, documentId, documentTitle, documentContent]);
}
