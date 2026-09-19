import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";
import AppContent from "@/components/AppContent";
import AgentSidebarGate from "@/components/AgentSidebarGate";
import { AgentProvider } from "@/lib/agentContext";

export const metadata: Metadata = {
  title: "DocuBear",
  description: "Automated code documentation, reviewed by you.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AgentProvider>
          <Navbar />
          <AppContent>
            <PageTransition>{children}</PageTransition>
          </AppContent>
          <AgentSidebarGate />
        </AgentProvider>
      </body>
    </html>
  );
}
