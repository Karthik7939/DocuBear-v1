"use client";

import { useState } from "react";
import DiffViewer, { DiffSummary } from "@/components/DiffViewer";

interface ProposalCardProps {
  proposalId: string;
  summary: string;
  rationale: string;
  before: string;
  after: string;
  /** Set once the proposal is resolved (applied/rejected/superseded) so the buttons disappear but the card stays in the transcript as a record. */
  status: "pending" | "applied" | "rejected";
  onApprove: (proposalId: string) => void;
  onReject: (proposalId: string, feedback?: string) => void;
}

export default function ProposalCard({
  proposalId,
  summary,
  rationale,
  before,
  after,
  status,
  onApprove,
  onReject,
}: ProposalCardProps) {
  const [showDiff, setShowDiff] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [feedback, setFeedback] = useState("");

  return (
    <div className="rounded-2xl border border-teal/30 bg-teal/5 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">
            Proposed Change
          </p>
          <p className="mt-1 text-xs font-semibold text-text">{summary}</p>
          {rationale && <p className="mt-0.5 text-[11px] text-muted leading-relaxed">{rationale}</p>}
        </div>
        <DiffSummary oldText={before} newText={after} />
      </div>

      <button
        onClick={() => setShowDiff((s) => !s)}
        className="text-[11px] font-bold text-teal hover:underline"
      >
        {showDiff ? "Hide diff" : "Show diff"}
      </button>

      {showDiff && (
        <div className="max-h-72 overflow-y-auto">
          <DiffViewer oldText={before} newText={after} />
        </div>
      )}

      {status === "pending" && !rejecting && (
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={() => onApprove(proposalId)}
            className="rounded-full bg-emerald-700 text-white text-[11px] font-bold uppercase tracking-wider px-4 py-2 hover:bg-emerald-800 transition-colors"
          >
            Approve
          </button>
          <button
            onClick={() => setRejecting(true)}
            className="rounded-full border border-border text-text text-[11px] font-bold uppercase tracking-wider px-4 py-2 hover:border-text/40 transition-colors"
          >
            Reject
          </button>
        </div>
      )}

      {status === "pending" && rejecting && (
        <div className="space-y-2 pt-1">
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Optional: what should be different instead?"
            rows={2}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-[11px] focus:outline-none focus:ring-2 focus:ring-teal/20 focus:border-teal placeholder:text-muted/60"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => onReject(proposalId, feedback.trim() || undefined)}
              className="rounded-full bg-rose-700 text-white text-[11px] font-bold uppercase tracking-wider px-4 py-2 hover:bg-rose-800 transition-colors"
            >
              Confirm Reject
            </button>
            <button
              onClick={() => setRejecting(false)}
              className="text-[11px] font-semibold text-muted hover:text-text px-2"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {status === "applied" && (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[10px] font-bold text-emerald-800">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Applied
        </span>
      )}
      {status === "rejected" && (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-canvas px-3 py-1 text-[10px] font-bold text-muted">
          Discarded
        </span>
      )}
    </div>
  );
}
