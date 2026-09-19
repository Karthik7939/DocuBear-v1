"use client";

import { useState } from "react";
import Link from "next/link";

interface ApprovalActionsProps {
  docId: string;
  onApprove?: () => void;
  onRevise?: (revisedDoc: any) => void;
}

export default function ApprovalActions({
  docId,
  onApprove,
  onRevise,
}: ApprovalActionsProps) {
  const [comment, setComment] = useState("");
  const [showComment, setShowComment] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");

  async function handleApprove() {
    setLoading(true);
    setLoadingText("Approving document...");
    try {
      await fetch("/api/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ docId }),
      });
      if (onApprove) onApprove();
    } catch (err) {
      console.error("Approve failed:", err);
    } finally {
      setLoading(false);
      setLoadingText("");
    }
  }

  async function handleRequestChanges() {
    if (!comment.trim()) return;
    setLoading(true);
    setLoadingText("Agent is revising documentation based on your request...");
    try {
      const res = await fetch("/api/reject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ docId, comment }),
      });
      const data = await res.json();
      if (onRevise) onRevise(data);
      setShowComment(false);
      setComment("");
    } catch (err) {
      console.error("Request changes failed:", err);
    } finally {
      setLoading(false);
      setLoadingText("");
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
      {loading ? (
        <div className="flex items-center gap-3 py-1 text-xs font-semibold uppercase tracking-wider text-teal">
          <svg className="w-4 h-4 animate-spin text-teal" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span>{loadingText}</span>
        </div>
      ) : !showComment ? (
        <div className="flex flex-wrap gap-3 items-center">
          {/* Approve Button - Presidio Dark Pill / Emerald option */}
          <button
            id="btn-approve"
            onClick={handleApprove}
            disabled={loading}
            className="bg-emerald-700 text-white text-xs font-semibold uppercase tracking-wider px-5 py-2.5 rounded-full hover:bg-emerald-800 transition-all disabled:opacity-50 flex items-center gap-1.5 shadow-xs"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            Approve Document
          </button>

          {/* Publish / Export Button - Presidio Teal Pill */}
          <Link
            id="btn-publish-redirect"
            href="/publish"
            className="inline-flex items-center gap-1.5 border border-teal/30 bg-teal/10 text-teal text-xs font-semibold uppercase tracking-wider px-5 py-2.5 rounded-full hover:bg-teal hover:text-white transition-all shadow-xs"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            Publish / Export
          </Link>

          {/* Request Changes Button - Presidio Golden CTA / Outlined Pill */}
          <button
            id="btn-request-changes"
            onClick={() => setShowComment(true)}
            disabled={loading}
            className="border border-border text-text text-xs font-semibold uppercase tracking-wider px-5 py-2.5 rounded-full hover:border-text hover:bg-canvas transition-all shadow-xs"
          >
            Request Changes
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <label className="block text-xs font-bold uppercase tracking-wider text-text">
            Specify changes for Revision Agent:
          </label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Describe what needs to be changed in the documentation (e.g. 'Add setup instructions for Docker', 'Update API endpoint details'...)"
            rows={3}
            className="w-full border border-border rounded-xl px-4 py-3 text-xs focus:outline-none focus:ring-2 focus:ring-teal/20 focus:border-teal font-sans text-text placeholder:text-muted/60 bg-canvas"
          />
          <div className="flex gap-3">
            <button
              onClick={handleRequestChanges}
              disabled={loading || !comment.trim()}
              className="bg-accent-cta text-text text-xs font-bold uppercase tracking-wider px-5 py-2.5 rounded-full hover:bg-yellow-300 transition-all disabled:opacity-50 flex items-center gap-1.5 shadow-xs"
            >
              Submit to Agent
            </button>
            <button
              onClick={() => setShowComment(false)}
              className="text-xs font-semibold uppercase tracking-wider text-muted hover:text-text px-3 py-2 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
