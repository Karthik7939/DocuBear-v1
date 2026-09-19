"use client";

import { usePathname } from "next/navigation";
import AgentSidebar from "./AgentSidebar";
import { isAssistantPage } from "@/lib/assistantPages";

/**
 * Mounts AgentSidebar only on the pages it's actually scoped to (see
 * lib/assistantPages.ts) instead of app-wide. Mounting/unmounting it per
 * route -- rather than always rendering it and just hiding its UI -- means
 * its Gemini Live session and mic capture are torn down (AgentSidebar's own
 * unmount cleanup) the moment the user navigates to a page where the
 * assistant isn't available, instead of lingering unseen in the background.
 */
export default function AgentSidebarGate() {
  const pathname = usePathname();
  if (!isAssistantPage(pathname)) return null;
  return <AgentSidebar />;
}
