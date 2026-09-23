import { db } from "@/lib/db";
import Link from "next/link";
import { DocVersion, Repo } from "@/types";
import { AnimatedContainer, AnimatedItem, ScrollReveal } from "@/components/AnimatedItem";

import HeroAnimatedTitle from "@/components/HeroAnimatedTitle";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const docs = await db.listDocs();
  const repos = await db.listRepos();

  const updatedDocsCount = docs.filter((d) => d.hasChanges).length;
  const publishedDocsCount = docs.filter(
    (d) => d.status === "published" || d.status === "approved"
  ).length;

  return (
    <div className="space-y-0 pb-0">

      {/* ── HERO BANNER — Presidio style: dark navy bg, bold serif-weight heading, golden CTA ── */}
      <section className="relative -mx-6 -mt-6 sm:-mx-10 lg:-mx-12 overflow-hidden bg-text px-6 py-16 sm:px-10 lg:px-12 sm:py-20">
        {/* Subtle teal gradient glow — bottom right like Presidio's image overlay */}
        <div className="pointer-events-none absolute bottom-0 right-0 h-96 w-96 rounded-full bg-teal/20 blur-3xl" />
        <div className="pointer-events-none absolute top-0 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-teal-light/10 blur-3xl" />

        <AnimatedContainer className="relative z-10 w-full">
          {/* Eyebrow — Presidio's small category label */}
          <AnimatedItem y={15}>
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-teal-light/80">
              Autonomous Documentation Engine
            </p>
          </AnimatedItem>

          <AnimatedItem y={20}>
            <HeroAnimatedTitle />
          </AnimatedItem>

          <AnimatedItem y={25}>
            <p className="mt-5 max-w-3xl text-base font-normal text-white/60 leading-relaxed">
              Automated repository analysis, incremental change tracking, and standard documentation sync — reviewed and published by your team.
            </p>
          </AnimatedItem>

          {/* CTA buttons — Presidio's golden pill primary + outlined secondary */}
          <AnimatedItem y={30}>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                href="/review"
                className="inline-flex items-center gap-2.5 rounded-full bg-teal text-white px-7 py-3.5 text-sm font-bold shadow-md hover:bg-teal/90 transition-all duration-200 active:scale-95"
              >
                Review Documents
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </Link>
              <Link
                href="/knowledge-base"
                className="inline-flex items-center gap-2 rounded-full border border-white/30 px-6 py-3 text-sm font-semibold text-white transition-all duration-200 hover:border-white/60 hover:bg-white/10"
              >
                Knowledge Base
              </Link>
            </div>
          </AnimatedItem>
        </AnimatedContainer>
      </section>

      {/* ── GRADIENT DIVIDER — Presidio's teal-to-navy bar ── */}
      <div className="h-1.5 w-full bg-presidio-gradient -mx-6 sm:-mx-10 lg:-mx-12" style={{ width: "calc(100% + 6rem)" }} />

      {/* ── KPI METRICS — Presidio's stat section on off-white bg ── */}
      <section className="-mx-6 sm:-mx-10 lg:-mx-12 bg-canvas px-6 py-12 sm:px-10 lg:px-12">
        <AnimatedContainer className="w-full">
          <AnimatedItem y={15}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-teal">
              System Overview
            </p>
          </AnimatedItem>
          <AnimatedItem y={20}>
            <h2 className="mb-8 text-2xl font-bold text-text">
              Everything running at a glance.
            </h2>
          </AnimatedItem>

          {/* Staggered entrance cards */}
          <div className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-4 rounded-xl overflow-hidden shadow-sm">
            {/* Metric 1 */}
            <AnimatedItem y={25}>
              <div className="group bg-surface p-7 hover:bg-accent-soft transition-colors duration-200 h-full">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted mb-3">Connected Projects</p>
                <p className="text-5xl font-bold text-text mb-1">{repos.length}</p>
                <p className="text-sm text-muted">Auto-synced via webhook</p>
                <div className="mt-4 h-0.5 w-8 bg-teal rounded-full" />
              </div>
            </AnimatedItem>
            {/* Metric 2 */}
            <AnimatedItem y={25}>
              <div className="group bg-surface p-7 hover:bg-accent-soft transition-colors duration-200 h-full">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted mb-3">Tracked Docs</p>
                <p className="text-5xl font-bold text-text mb-1">{docs.length}</p>
                <p className="text-sm text-muted">README, Arch, Changelog, Security</p>
                <div className="mt-4 h-0.5 w-8 bg-teal rounded-full" />
              </div>
            </AnimatedItem>
            {/* Metric 3 */}
            <AnimatedItem y={25}>
              <div className="group bg-surface p-7 hover:bg-accent-soft transition-colors duration-200 h-full">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted mb-3">Pending Updates</p>
                <p className="text-5xl font-bold text-text mb-1">{updatedDocsCount}</p>
                <p className="text-sm text-muted">
                  {updatedDocsCount > 0 ? "Requires your attention" : "All up to date"}
                </p>
                <div className={`mt-4 h-0.5 w-8 rounded-full ${updatedDocsCount > 0 ? "bg-yellow-400" : "bg-teal"}`} />
              </div>
            </AnimatedItem>
            {/* Metric 4 */}
            <AnimatedItem y={25}>
              <div className="group bg-surface p-7 hover:bg-accent-soft transition-colors duration-200 h-full">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted mb-3">Reviewed Docs</p>
                <p className="text-5xl font-bold text-text mb-1">{publishedDocsCount}</p>
                <p className="text-sm text-muted">
                  {docs.length > 0 ? `${Math.round((publishedDocsCount / docs.length) * 100)}% approval rate` : "No docs yet"}
                </p>
                <div className="mt-4 h-0.5 w-8 bg-emerald-500 rounded-full" />
              </div>
            </AnimatedItem>
          </div>
        </AnimatedContainer>
      </section>

      {/* ── MAIN CONTENT — white bg, two-column Presidio layout ── */}
      <section className="-mx-6 sm:-mx-10 lg:-mx-12 bg-surface px-6 py-12 sm:px-10 lg:px-12">
        <AnimatedContainer className="w-full grid gap-12 lg:grid-cols-3">

          {/* LEFT — Recent Documentation (2/3) */}
          <div className="lg:col-span-2 space-y-6">
            <AnimatedItem y={20}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal mb-1">Documentation Hub</p>
                  <h2 className="text-xl font-bold text-text">Recent Documentation</h2>
                  <p className="mt-1 text-sm text-muted">
                    Generated project overview, architecture, and security specifications.
                  </p>
                </div>
                <Link
                  href="/review"
                  className="flex-shrink-0 inline-flex items-center gap-1 rounded-full border border-text/20 px-4 py-1.5 text-xs font-semibold text-text hover:bg-canvas transition-colors"
                >
                  View All ({docs.length})
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </Link>
              </div>
            </AnimatedItem>

            {docs.length === 0 ? (
              <AnimatedItem y={25}>
                <div className="rounded-2xl border border-border bg-accent-soft p-12 text-center">
                  <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-teal/10 text-teal">
                    <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                    </svg>
                  </div>
                  <h3 className="text-base font-bold text-text mb-1">No documentation generated yet</h3>
                  <p className="text-sm text-muted max-w-sm mx-auto">
                    Connect a GitHub repository to trigger the automated RAG understanding and documentation pipeline.
                  </p>
                </div>
              </AnimatedItem>
            ) : (
              <div className="space-y-2">
                {docs.map((doc) => (
                  <AnimatedItem key={doc.id} y={20}>
                    <div
                      className="group flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border border-border bg-surface p-4 transition-all duration-200 hover:border-teal/40 hover:shadow-sm"
                    >
                      <div className="flex items-start gap-4 min-w-0">
                        <DocTypeIcon title={doc.title} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-teal">
                              {getDocCategory(doc.title)}
                            </span>
                            {doc.hasChanges && (
                              <span className="rounded-full bg-yellow-100 border border-yellow-300 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-yellow-800">
                                Modified
                              </span>
                            )}
                          </div>
                          <h4 className="mt-0.5 text-sm font-bold text-text truncate group-hover:text-teal transition-colors">
                            {doc.title.split("/").at(-1)}
                          </h4>
                          <p className="text-[11px] text-muted font-mono truncate mt-0.5 opacity-70">
                            {doc.title}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center justify-between sm:justify-end gap-3 flex-shrink-0 pt-3 sm:pt-0 border-t sm:border-t-0 border-border/60">
                        <StatusBadge status={doc.status} />
                        <Link
                          href={`/review/${doc.id}`}
                          className="inline-flex items-center gap-1.5 rounded-full border border-text/20 bg-text px-4 py-1.5 text-[12px] font-semibold text-white transition-all hover:bg-text/80"
                        >
                          Review
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                          </svg>
                        </Link>
                      </div>
                    </div>
                  </AnimatedItem>
                ))}
              </div>
            )}
          </div>

          {/* RIGHT — Sidebar (1/3) */}
          <div className="space-y-8">

            {/* Connected Repositories */}
            <AnimatedItem y={20}>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal mb-1">Repositories</p>
                <h3 className="text-base font-bold text-text mb-4">Connected Projects</h3>
                <div className="space-y-2">
                  {repos.length === 0 ? (
                    <p className="text-sm text-muted p-4 bg-accent-soft rounded-xl border border-border">
                      No repositories connected.
                    </p>
                  ) : (
                    repos.map((repo) => (
                      <div
                        key={repo.id}
                        className="flex items-center justify-between rounded-xl bg-accent-soft border border-border px-4 py-3 hover:border-teal/40 transition-colors"
                      >
                        <div className="min-w-0 flex items-center gap-3 pr-2">
                          <div className="flex-shrink-0 h-7 w-7 rounded-full bg-presidio-gradient flex items-center justify-center">
                            <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                            </svg>
                          </div>
                          <div>
                            <p className="text-xs font-bold text-text truncate">{repo.fullName}</p>
                            <p className="text-[10px] font-mono text-muted">main branch</p>
                          </div>
                        </div>
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[9px] font-bold text-emerald-700 flex-shrink-0">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Active
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </AnimatedItem>

            {/* Quick Integration Hub */}
            <AnimatedItem y={25}>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal mb-1">Integrations</p>
                <h3 className="text-base font-bold text-text mb-4">Quick Access</h3>

                <div className="space-y-2">
                  {[
                    {
                      href: "/knowledge-base",
                      label: "VECTOR STORE",
                      title: "Knowledge Base",
                      desc: "Manage vector embeddings and RAG context",
                      icon: (
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s-8-1.79-8-4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                        </svg>
                      ),
                    },
                    {
                      href: "/publish",
                      label: "PUBLISH",
                      title: "Publish & Export",
                      desc: "Publish docs to GitBook or export as PDF",
                      icon: (
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                        </svg>
                      ),
                    },
                  ].map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className="group flex items-center gap-4 rounded-xl border border-border bg-accent-soft p-4 transition-all duration-200 hover:border-teal/50 hover:bg-surface"
                    >
                      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-text/5 text-text group-hover:bg-teal/10 group-hover:text-teal transition-colors">
                        {item.icon}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-teal mb-0.5">{item.label}</p>
                        <p className="text-xs font-bold text-text">{item.title}</p>
                        <p className="text-[11px] text-muted">{item.desc}</p>
                      </div>
                      <svg className="w-4 h-4 text-muted group-hover:text-teal transition-colors flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                    </Link>
                  ))}
                </div>
              </div>
            </AnimatedItem>
          </div>
        </AnimatedContainer>
      </section>

    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function getDocCategory(title: string): string {
  const f = title.split("/").at(-1)?.toUpperCase() || "";
  if (f.includes("README")) return "ReadMe";
  if (f.includes("ARCHITECTURE")) return "Architecture";
  if (f.includes("REQUIREMENT")) return "Requirements";
  if (f.includes("WORKFLOW")) return "Workflow";
  if (f.includes("REPORTS")) return "Reports";
  if (f.includes("CHANGELOG")) return "Changelog";
  if (f.includes("SECURITY")) return "Security";
  return "Document";
}

function DocTypeIcon({ title }: { title: string }) {
  const filename = title.split("/").at(-1)?.toUpperCase() || "";
  const configs: Record<string, { bg: string; icon: React.ReactNode }> = {
    README: {
      bg: "bg-teal/10 text-teal border-teal/20",
      icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>,
    },
    ARCHITECTURE: {
      bg: "bg-text/5 text-text border-border",
      icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>,
    },
    REQUIREMENTS: {
      bg: "bg-indigo-50 text-indigo-600 border-indigo-200",
      icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>,
    },
    WORKFLOW: {
      bg: "bg-amber-50 text-amber-600 border-amber-200",
      icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>,
    },
    REPORTS: {
      bg: "bg-purple-50 text-purple-600 border-purple-200",
      icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>,
    },
    CHANGELOG: {
      bg: "bg-teal/10 text-teal border-teal/20",
      icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
    },
    SECURITY: {
      bg: "bg-text/5 text-text border-border",
      icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>,
    },
  };

  let key = "DEFAULT";
  if (filename.includes("README")) key = "README";
  else if (filename.includes("ARCHITECTURE")) key = "ARCHITECTURE";
  else if (filename.includes("REQUIREMENT")) key = "REQUIREMENTS";
  else if (filename.includes("WORKFLOW")) key = "WORKFLOW";
  else if (filename.includes("REPORTS")) key = "REPORTS";
  else if (filename.includes("CHANGELOG")) key = "CHANGELOG";
  else if (filename.includes("SECURITY")) key = "SECURITY";

  const cfg = configs[key] ?? {
    bg: "bg-text/5 text-text border-border",
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>,
  };

  return (
    <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border ${cfg.bg}`}>
      {cfg.icon}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    draft: "bg-slate-100 text-slate-600 border-slate-200",
    pending_review: "bg-yellow-50 text-yellow-800 border-yellow-300",
    approved: "bg-emerald-50 text-emerald-800 border-emerald-200",
    changes_requested: "bg-rose-50 text-rose-800 border-rose-200",
    published: "bg-teal/10 text-teal border-teal/30",
  };
  return (
    <span className={`text-[10px] px-3 py-1 rounded-full font-bold uppercase tracking-wider border ${styles[status] || "bg-slate-100 text-slate-600 border-slate-200"}`}>
      {status.replace("_", " ")}
    </span>
  );
}
