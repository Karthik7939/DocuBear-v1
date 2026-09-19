/**
 * lib/assistantPages.ts
 * ------------------------
 * The AgentSidebar assistant only makes sense where there's a document to
 * discuss/edit (the Documentation review page) or a file to generate docs
 * for (File Docs) -- everywhere else there's nothing for it to be scoped
 * to. Shared by AgentSidebarGate (mounts/unmounts the sidebar itself) and
 * AppContent (reserves layout space for it) so both agree on exactly the
 * same set of pages.
 */

const ASSISTANT_PAGE_PREFIXES = ["/review", "/file-docs"];

export function isAssistantPage(pathname: string): boolean {
  return ASSISTANT_PAGE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}
