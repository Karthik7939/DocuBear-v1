"use client";

import { useAgentContext } from "@/lib/agentContext";

/**
 * Wraps the page content and reserves space on the right for the persistent
 * AgentSidebar when it's open, so the sidebar overlays nothing -- content
 * reflows instead of being covered. On narrower screens there isn't room to
 * reflow sensibly, so the sidebar just overlays there instead.
 */
export default function AppContent({ children }: { children: React.ReactNode }) {
  const { sidebarCollapsed } = useAgentContext();

  return (
    <main
      className={`w-full px-6 py-6 sm:px-10 lg:px-12 transition-[padding] duration-300 ease-out ${
        sidebarCollapsed ? "" : "lg:pr-[452px]"
      }`}
    >
      {children}
    </main>
  );
}
