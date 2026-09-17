"use client";

import { useState } from "react";
import DocPreview from "@/components/DocPreview";
import ApprovalActions from "@/components/ApprovalActions";
import { DiffSummary } from "@/components/DiffViewer";
import { DocVersion } from "@/types";
import { AnimatedContainer, AnimatedItem } from "@/components/AnimatedItem";
import { useRegisterOpenDocument } from "@/lib/agentContext";

export default function DocReviewClient({ initialDoc }: { initialDoc: DocVersion }) {
  const [doc, setDoc] = useState<DocVersion>(initialDoc);

  const handleApprove = () => {
    setDoc((prev) => ({
      ...prev,
      previousContent: undefined,
      hasChanges: false,
      status: "approved",
    }));
  };

  const handleRevise = (updatedDoc: any) => {
    if (updatedDoc && updatedDoc.content) {
      setDoc((prev) => ({
        ...prev,
        content: updatedDoc.content,
        previousContent: updatedDoc.previous_content || updatedDoc.previousContent || prev.content,
        hasChanges: Boolean(updatedDoc.previous_content || updatedDoc.previousContent),
        status: "changes_requested",
      }));
    }
  };

  const handleSave = (updatedDoc: any) => {
    if (updatedDoc && updatedDoc.content) {
      setDoc((prev) => ({
        ...prev,
        content: updatedDoc.content,
        previousContent: updatedDoc.previous_content || updatedDoc.previousContent || prev.previousContent,
        hasChanges: Boolean(updatedDoc.previous_content || updatedDoc.previousContent || prev.previousContent),
      }));
    }
  };

  const handleAssistantChange = (newContent: string, previousContent: string) => {
    setDoc((prev) => ({
      ...prev,
      content: newContent,
      previousContent,
      hasChanges: true,
      status: "changes_requested",
    }));
  };

  const fileName = doc.title.split("/").at(-1) || doc.title;
  const folderPath = doc.title.split("/").slice(0, -1).join("/") || "root";

  // doc.repoId is the underscored slug used on disk (e.g. "Owner_repo-name");
  // the chat backend expects the "owner/repo" form, same as GitHub's full_name.
  const repositoryName = doc.repoId.replace("_", "/");

  // Tell the persistent, layout-level AgentSidebar which document is open —
  // it lives outside this page so it survives navigation instead of being
  // torn down and rebuilt every time.
  useRegisterOpenDocument({
    repositoryName,
    documentId: doc.id,
    documentTitle: fileName,
    documentContent: doc.content,
    onDocumentChanged: handleAssistantChange,
  });

  return (
    <>
      <AnimatedContainer className="space-y-6 pb-12">
      {/* Document Header Card */}
      <AnimatedItem y={15}>
        <div className="relative overflow-hidden rounded-2xl border border-border bg-surface p-6 shadow-sm">
          {/* Top teal gradient accent line */}
          <div className="absolute top-0 left-0 right-0 h-1 bg-presidio-gradient" />

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1.5 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">
                  SPECIFICATION REVIEW
                </span>
                {doc.previousContent && (
                  <span className="inline-flex items-center">
                    <DiffSummary oldText={doc.previousContent} newText={doc.content} />
                  </span>
                )}
              </div>

              <h1 className="text-2xl font-extrabold tracking-tight text-text truncate">
                {fileName}
              </h1>

              <p className="text-xs font-mono text-muted truncate opacity-80">
                {doc.title}
              </p>
            </div>

            <div className="flex items-center gap-3 shrink-0 self-start md:self-auto">
              <span className="text-xs text-muted font-medium">
                {/* Explicit locale so server (Node's default ICU locale) and
                    client (the browser's locale) always format identically —
                    an unspecified locale here caused a hydration mismatch. */}
                {new Date(doc.createdAt).toLocaleDateString("en-US")}
              </span>

              {doc.previousContent ? (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-yellow-300 bg-yellow-50 px-3 py-1 text-xs font-bold text-yellow-800">
                  <span className="h-2 w-2 rounded-full bg-yellow-400 animate-pulse" />
                  Diff Mode (Modified)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-800">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Approved Version
                </span>
              )}
            </div>
          </div>
        </div>
      </AnimatedItem>

      {/* Approval & Revision Agent Action Panel */}
      <AnimatedItem y={20}>
        <ApprovalActions
          docId={doc.id}
          onApprove={handleApprove}
          onRevise={handleRevise}
        />
      </AnimatedItem>

      {/* Main Tabbed Document Preview / Manual Editor / Diff Viewer */}
      <AnimatedItem y={25}>
        <DocPreview
          key={`${doc.id}-${doc.previousContent ? 'diff' : 'clean'}-${doc.content.length}`}
          docId={doc.id}
          content={doc.content}
          previousContent={doc.previousContent}
          onSave={handleSave}
        />
      </AnimatedItem>
      </AnimatedContainer>
    </>
  );
}
