"use client";

import { usePathname } from "next/navigation";
import { useAgentContext } from "@/lib/agentContext";
import { isAssistantPage } from "@/lib/assistantPages";

/**
 * Wraps the page content and reserves space on the right for AgentSidebar
 * when it's open, so the sidebar overlays nothing -- content reflows
 * instead of being covered. On narrower screens there isn't room to reflow
 * sensibly, so the sidebar just overlays there instead. Only reserves that
 * space on the pages AgentSidebarGate actually mounts the sidebar on --
 * elsewhere sidebarCollapsed may still say "open" from a previous page, but
 * there's no sidebar there to make room for.
 */
export default function AppContent({ children }: { children: React.ReactNode }) {
  const { sidebarCollapsed } = useAgentContext();
  const pathname = usePathname();
  const reserveSpace = !sidebarCollapsed && isAssistantPage(pathname);

  return (
    <main
      className={`w-full px-6 py-6 sm:px-10 lg:px-12 transition-[padding] duration-300 ease-out ${
        reserveSpace ? "lg:pr-[452px]" : ""
      }`}
    >
      {children}
    </main>
  );
}
