"use client";

import { useCallback, useEffect, useRef, useState, KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MermaidDiagram from "./MermaidDiagram";
import ProposalCard from "./ProposalCard";
import { VoiceChatClient, VoiceEvent } from "@/lib/voiceChatClient";
import { PcmAudioCapture, PcmAudioPlayer } from "@/lib/audioIO";
import { useAgentContext } from "@/lib/agentContext";

interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

interface ProposalState {
  id: string;
  summary: string;
  rationale: string;
  before: string;
  after: string;
  status: "pending" | "applied" | "rejected";
}

type TranscriptItem =
  | { kind: "text"; id: string; role: "user" | "assistant"; content: string; streaming?: boolean }
  | { kind: "proposal"; id: string; proposal: ProposalState }
  | { kind: "system"; id: string; content: string };

const MAX_STORED_TURNS = 40;
const SIDEBAR_WIDTH = 420;

function storageKey(repositoryName: string): string {
  return `docubear_chat:${repositoryName}`;
}

function loadHistory(repositoryName: string): ChatTurn[] {
  try {
    const raw = window.localStorage.getItem(storageKey(repositoryName));
    return raw ? (JSON.parse(raw) as ChatTurn[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(repositoryName: string, messages: ChatTurn[]): void {
  try {
    window.localStorage.setItem(storageKey(repositoryName), JSON.stringify(messages.slice(-MAX_STORED_TURNS)));
  } catch {
    // Storage unavailable -- chat still works, just won't persist.
  }
}

let uidCounter = 0;
function nextId(): string {
  uidCounter += 1;
  return `t${Date.now()}_${uidCounter}`;
}

function MarkdownBubble({ content }: { content: string }) {
  return (
    <div className="prose prose-sm prose-slate max-w-none prose-headings:font-bold prose-headings:text-text prose-a:text-teal prose-code:text-teal prose-code:bg-teal/5 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children }: any) {
            return (
              <pre className="has-[.mermaid-diagram-card]:bg-transparent has-[.mermaid-diagram-card]:p-0 has-[.mermaid-diagram-card]:my-0 bg-text text-white rounded-xl p-3 my-2 overflow-x-auto">
                {children}
              </pre>
            );
          },
          code({ inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || "");
            if (match && match[1] === "mermaid") {
              return <MermaidDiagram chart={String(children).replace(/\n$/, "")} />;
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/** Three-dot "someone is speaking" indicator, shown while the mic is held. */
function SpeakingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-hidden="true">
      <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce" />
    </span>
  );
}

export default function AgentSidebar() {
  const { openDocument, sidebarCollapsed, setSidebarCollapsed } = useAgentContext();
  const repositoryName = openDocument?.repositoryName;
  const documentId = openDocument?.documentId;
  const documentTitle = openDocument?.documentTitle;

  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [sessionItems, setSessionItems] = useState<TranscriptItem[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [sessionActive, setSessionActive] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [micHeld, setMicHeld] = useState(false);
  const [assistantSpeaking, setAssistantSpeaking] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const clientRef = useRef<VoiceChatClient | null>(null);
  const captureRef = useRef<PcmAudioCapture | null>(null);
  const playerRef = useRef<PcmAudioPlayer | null>(null);
  const streamingAssistantIdRef = useRef<string | null>(null);
  const streamingUserIdRef = useRef<string | null>(null);
  // Which modality produced the turn currently in flight -- gates whether
  // the assistant's audio actually gets played (text in -> text-only reply;
  // voice in -> text + spoken reply), independent of the fact that Gemini
  // always streams both back.
  const lastInputModeRef = useRef<"text" | "voice">("text");
  // Set by the Stop button so any remaining chunks for the turn already in
  // flight are dropped instead of played -- reset whenever a new turn
  // starts (Gemini keeps streaming the rest of the reply after a manual
  // stop; we just stop listening to its audio).
  const suppressAudioRef = useRef(false);
  // "repo::docId" of the document the current/pending session is scoped to,
  // so a change can be told apart from a first connect.
  const connectedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!repositoryName) {
      setMessages([]);
      return;
    }
    setMessages(loadHistory(repositoryName));
    setError(null);
  }, [repositoryName]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sessionItems, loading, sidebarCollapsed]);

  const appendSessionItem = useCallback((item: TranscriptItem) => {
    setSessionItems((prev) => [...prev, item]);
  }, []);

  const updateProposal = useCallback((id: string, patch: Partial<ProposalState>) => {
    setSessionItems((prev) =>
      prev.map((item) =>
        item.kind === "proposal" && item.proposal.id === id
          ? { ...item, proposal: { ...item.proposal, ...patch } }
          : item
      )
    );
  }, []);

  // ------------------------------------------------------------------
  // Voice/agent session lifecycle
  // ------------------------------------------------------------------

  const endSession = useCallback(() => {
    captureRef.current?.stop();
    captureRef.current = null;
    playerRef.current?.close();
    playerRef.current = null;
    clientRef.current?.close();
    clientRef.current = null;
    streamingAssistantIdRef.current = null;
    streamingUserIdRef.current = null;
    suppressAudioRef.current = false;
    setSessionActive(false);
    setConnecting(false);
    setMicHeld(false);
    setAssistantSpeaking(false);
  }, []);

  const handleVoiceEvent = useCallback(
    (event: VoiceEvent) => {
      switch (event.type) {
        case "ready": {
          setConnecting(false);
          setSessionActive(true);
          break;
        }
        case "partial_transcript": {
          if (streamingUserIdRef.current) {
            const id = streamingUserIdRef.current;
            setSessionItems((prev) =>
              prev.map((it) => (it.kind === "text" && it.id === id ? { ...it, content: event.text } : it))
            );
          } else {
            const id = nextId();
            streamingUserIdRef.current = id;
            appendSessionItem({ kind: "text", id, role: "user", content: event.text, streaming: true });
          }
          break;
        }
        case "assistant_text_delta": {
          if (streamingAssistantIdRef.current) {
            const id = streamingAssistantIdRef.current;
            setSessionItems((prev) =>
              prev.map((it) =>
                it.kind === "text" && it.id === id ? { ...it, content: it.content + event.text } : it
              )
            );
          } else {
            const id = nextId();
            streamingAssistantIdRef.current = id;
            appendSessionItem({ kind: "text", id, role: "assistant", content: event.text, streaming: true });
          }
          break;
        }
        case "assistant_audio_chunk": {
          // Gemini always streams audio back; only actually play it when the
          // triggering turn was spoken, so a typed question gets a text-only
          // reply and a spoken one gets voice + text. suppressAudioRef lets
          // the Stop button silence the rest of an in-flight reply even
          // though Gemini keeps streaming chunks until the turn ends.
          if (lastInputModeRef.current === "voice" && !suppressAudioRef.current) {
            playerRef.current?.enqueuePcm16(event.data);
            setAssistantSpeaking(true);
          }
          break;
        }
        case "assistant_turn_complete": {
          streamingAssistantIdRef.current = null;
          streamingUserIdRef.current = null;
          setSessionItems((prev) => prev.map((it) => (it.kind === "text" ? { ...it, streaming: false } : it)));
          setAssistantSpeaking(false);
          break;
        }
        case "proposal": {
          appendSessionItem({
            kind: "proposal",
            id: nextId(),
            proposal: {
              id: event.proposal_id,
              summary: event.summary,
              rationale: event.rationale,
              before: event.diff.before,
              after: event.diff.after,
              status: "pending",
            },
          });
          break;
        }
        case "proposal_applied": {
          updateProposal(event.proposal_id, { status: "applied" });
          openDocument?.onDocumentChanged?.(event.new_content, event.previous_content);
          break;
        }
        case "proposal_rejected": {
          updateProposal(event.proposal_id, { status: "rejected" });
          break;
        }
        case "error": {
          appendSessionItem({ kind: "system", id: nextId(), content: `⚠️ ${event.message}` });
          break;
        }
        case "closed": {
          endSession();
          break;
        }
      }
    },
    [appendSessionItem, updateProposal, openDocument, endSession]
  );

  const startSession = useCallback(async () => {
    // clientRef is the synchronous source of truth (state updates are
    // batched/async, which would otherwise race with the doc-switch effect
    // below that ends and immediately restarts a session in one tick).
    if (!documentId || !repositoryName || clientRef.current) return;
    setConnecting(true);
    setError(null);
    const client = new VoiceChatClient();
    clientRef.current = client;
    client.onEvent(handleVoiceEvent);
    try {
      await client.connect({ documentId, repositoryName });
      playerRef.current = new PcmAudioPlayer();
    } catch (err) {
      setConnecting(false);
      setError(err instanceof Error ? err.message : "Could not connect to the assistant.");
      clientRef.current = null;
    }
  }, [documentId, repositoryName, handleVoiceEvent]);

  const stopSession = useCallback(() => {
    endSession();
    appendSessionItem({ kind: "system", id: nextId(), content: "You ended the assistant session." });
  }, [endSession, appendSessionItem]);

  // Interrupts the assistant's speech without ending the session -- Gemini
  // keeps streaming audio for the reply already in flight, so this both
  // silences what's queued/playing right now and drops any further chunks
  // until the next turn starts.
  const handleStopAudio = useCallback(() => {
    playerRef.current?.stopAndClear();
    suppressAudioRef.current = true;
    setAssistantSpeaking(false);
  }, []);

  // Auto-connect the tool-enabled session whenever a document is open and
  // the panel is visible, and silently re-scope it (no user-visible churn)
  // if the open document changes -- e.g. navigating to a different page or
  // selecting a different file. The sidebar itself never unmounts, so its
  // open/closed state and conversation persist across navigation; only the
  // underlying connection swaps to stay pinned to whichever one document is
  // now open, since edit scope must always match the viewer.
  useEffect(() => {
    const key = repositoryName && documentId ? `${repositoryName}::${documentId}` : null;
    const switchedDocument = connectedKeyRef.current !== null && connectedKeyRef.current !== key;
    if (switchedDocument) {
      endSession();
      setSessionItems([]);
    }
    connectedKeyRef.current = key;

    if (!sidebarCollapsed && documentId && repositoryName) {
      startSession();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repositoryName, documentId, sidebarCollapsed]);

  // ------------------------------------------------------------------
  // Push-to-talk
  // ------------------------------------------------------------------

  const handleMicDown = useCallback(async () => {
    if (!sessionActive || micHeld || !clientRef.current) return;
    setMicHeld(true);
    lastInputModeRef.current = "voice";
    playerRef.current?.stopAndClear(); // barge-in: stop assistant audio if it's still playing
    suppressAudioRef.current = false; // this new turn's reply should still be heard
    setAssistantSpeaking(false);
    clientRef.current.startAudioTurn();
    const capture = new PcmAudioCapture();
    captureRef.current = capture;
    try {
      await capture.start((chunk) => clientRef.current?.sendAudioChunk(chunk));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access failed.");
      setMicHeld(false);
      captureRef.current = null;
    }
  }, [sessionActive, micHeld]);

  const handleMicUp = useCallback(() => {
    if (!micHeld) return;
    captureRef.current?.stop();
    captureRef.current = null;
    clientRef.current?.endAudioTurn();
    setMicHeld(false);
  }, [micHeld]);

  // ------------------------------------------------------------------
  // Text input -- routed through the tool-enabled session whenever a
  // document is open (so editing is always available from the same box the
  // user is typing into); REST-only fallback when there's no document to
  // scope edits to in the first place (e.g. no file selected yet).
  // ------------------------------------------------------------------

  async function handleSend() {
    const question = input.trim();
    if (!question || loading) return;
    setInput("");
    setError(null);
    lastInputModeRef.current = "text";
    suppressAudioRef.current = false;

    if (documentId && repositoryName) {
      if (!clientRef.current) {
        await startSession();
      }
      appendSessionItem({ kind: "text", id: nextId(), role: "user", content: question });
      clientRef.current?.sendText(question);
      return;
    }

    if (!repositoryName) return;

    const historyBeforeThisTurn = messages;
    const withUserTurn: ChatTurn[] = [...messages, { role: "user", content: question }];
    setMessages(withUserTurn);
    saveHistory(repositoryName, withUserTurn);
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repositoryName, question, history: historyBeforeThisTurn }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || "Chat request failed");
      const withAnswer: ChatTurn[] = [...withUserTurn, { role: "assistant", content: data.answer }];
      setMessages(withAnswer);
      saveHistory(repositoryName, withAnswer);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    if (repositoryName) saveHistory(repositoryName, []);
    setMessages([]);
    setSessionItems([]);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const hasAnyMessages = messages.length > 0 || sessionItems.length > 0;
  const canChat = Boolean(repositoryName);

  return (
    <>
      {/* Collapsed rail toggle */}
      {sidebarCollapsed && (
        <button
          onClick={() => setSidebarCollapsed(false)}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-50 flex flex-col items-center gap-2 rounded-l-2xl border border-r-0 border-border bg-text text-white px-3 py-4 shadow-lg hover:bg-accent transition-all"
          aria-label="Open documentation assistant"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <span className="text-[10px] font-bold uppercase tracking-wider [writing-mode:vertical-rl]">Assistant</span>
        </button>
      )}

      {/* Sidebar panel */}
      {!sidebarCollapsed && (
        <div
          style={{ width: SIDEBAR_WIDTH }}
          className="fixed right-0 top-0 z-50 flex h-screen w-full max-w-[420px] flex-col border-l border-border bg-surface shadow-2xl"
        >
          {/* Header */}
          <div className="relative flex items-center justify-between border-b border-border px-4 py-3 shrink-0">
            <div className="absolute top-0 left-0 right-0 h-1 bg-presidio-gradient" />
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">Documentation Assistant</p>
              {repositoryName ? (
                <>
                  <p className="text-xs font-mono text-muted truncate">{repositoryName}</p>
                  {documentTitle && (
                    <p className="text-[11px] font-semibold text-text truncate">Editing: {documentTitle}</p>
                  )}
                </>
              ) : (
                <p className="text-xs text-muted truncate">No repository open</p>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {hasAnyMessages && (
                <button
                  onClick={handleClear}
                  className="text-[10px] font-bold uppercase tracking-wider text-muted hover:text-danger transition-colors"
                >
                  Clear
                </button>
              )}
              <button
                onClick={() => setSidebarCollapsed(true)}
                className="flex h-7 w-7 items-center justify-center rounded-full border border-border text-muted hover:text-text hover:border-text/40 transition-all"
                aria-label="Collapse sidebar"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>

          {/* Assistant session status -- connects automatically once a
              document is open, so editing/voice tools are always available
              without a separate "start" step. */}
          {documentId && (
            <div className="border-b border-border px-4 py-2 shrink-0">
              {connecting ? (
                <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Connecting...
                </span>
              ) : sessionActive ? (
                <button
                  onClick={stopSession}
                  className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-muted hover:text-rose-700 transition-colors"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Assistant live — End session
                </button>
              ) : (
                <button
                  onClick={startSession}
                  className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-rose-700 hover:underline"
                >
                  Disconnected — Reconnect
                </button>
              )}
            </div>
          )}

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {!canChat && (
              <p className="text-xs text-muted leading-relaxed">
                Open a repository's documentation to start chatting with the assistant.
              </p>
            )}

            {canChat && !hasAnyMessages && (
              <p className="text-xs text-muted leading-relaxed">
                {documentId
                  ? "Ask me anything about this repository, or ask for a change to this document — I'll draft it and wait for your approval. Hold the mic button to talk instead of typing."
                  : "Ask me anything about this repository. Open a document to also enable editing and voice."}
              </p>
            )}

            {messages.map((m, i) => (
              <div key={`m${i}`} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "assistant" ? (
                  <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-canvas px-3.5 py-2.5 text-xs text-text">
                    <MarkdownBubble content={m.content} />
                  </div>
                ) : (
                  <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-text text-white px-3.5 py-2.5 text-xs whitespace-pre-wrap">
                    {m.content}
                  </div>
                )}
              </div>
            ))}

            {sessionItems.map((item) => {
              if (item.kind === "system") {
                return (
                  <p key={item.id} className="text-center text-[11px] font-semibold text-muted py-1">
                    {item.content}
                  </p>
                );
              }
              if (item.kind === "proposal") {
                return (
                  <ProposalCard
                    key={item.id}
                    proposalId={item.proposal.id}
                    summary={item.proposal.summary}
                    rationale={item.proposal.rationale}
                    before={item.proposal.before}
                    after={item.proposal.after}
                    status={item.proposal.status}
                    onApprove={(id) => clientRef.current?.approveProposal(id)}
                    onReject={(id, feedback) => clientRef.current?.rejectProposal(id, feedback)}
                  />
                );
              }
              return (
                <div key={item.id} className={`flex ${item.role === "user" ? "justify-end" : "justify-start"}`}>
                  {item.role === "assistant" ? (
                    <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-canvas px-3.5 py-2.5 text-xs text-text">
                      <MarkdownBubble content={item.content || "…"} />
                    </div>
                  ) : (
                    <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-text text-white px-3.5 py-2.5 text-xs whitespace-pre-wrap">
                      {item.content || "…"}
                    </div>
                  )}
                </div>
              );
            })}

            {loading && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm border border-border bg-canvas px-3.5 py-2.5">
                  <svg className="w-4 h-4 animate-spin text-teal" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                </div>
              </div>
            )}

            {error && <p className="text-[11px] font-semibold text-danger">{error}</p>}
          </div>

          {/* Input */}
          <div className="border-t border-border p-3 shrink-0">
            {micHeld && (
              <div className="mb-2 flex items-center justify-center gap-2 rounded-full bg-rose-50 border border-rose-200 py-1.5 text-rose-700">
                <SpeakingDots />
                <span className="text-[10px] font-bold uppercase tracking-wider">Listening...</span>
              </div>
            )}
            {!micHeld && assistantSpeaking && (
              <div className="mb-2 flex items-center justify-between gap-2 rounded-full bg-teal/10 border border-teal/30 py-1.5 pl-3.5 pr-1.5 text-teal">
                <span className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider">
                  <SpeakingDots />
                  Assistant speaking...
                </span>
                <button
                  onClick={handleStopAudio}
                  className="flex items-center gap-1 rounded-full bg-teal text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 hover:bg-teal/80 transition-colors"
                  aria-label="Stop audio"
                >
                  <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="6" width="12" height="12" rx="1.5" />
                  </svg>
                  Stop
                </button>
              </div>
            )}
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={canChat ? "Ask a question, or type a change request..." : "Open a repository first..."}
                rows={1}
                disabled={!canChat}
                className="flex-1 resize-none rounded-xl border border-border bg-canvas px-3 py-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal/20 focus:border-teal placeholder:text-muted/60 disabled:opacity-50"
              />

              {documentId && (
                <button
                  onMouseDown={handleMicDown}
                  onMouseUp={handleMicUp}
                  onMouseLeave={handleMicUp}
                  onTouchStart={(e) => {
                    e.preventDefault();
                    handleMicDown();
                  }}
                  onTouchEnd={(e) => {
                    e.preventDefault();
                    handleMicUp();
                  }}
                  disabled={!sessionActive}
                  title={sessionActive ? "Hold to talk" : "Connecting..."}
                  className={`shrink-0 rounded-full p-2.5 transition-all select-none disabled:opacity-40 disabled:cursor-not-allowed ${
                    micHeld ? "bg-rose-600 text-white animate-pulse" : "bg-text text-white hover:bg-accent"
                  }`}
                  aria-label="Hold to talk"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
                  </svg>
                </button>
              )}

              <button
                onClick={handleSend}
                disabled={!canChat || loading || !input.trim()}
                className="shrink-0 rounded-full bg-accent-cta text-text p-2.5 hover:bg-yellow-300 transition-all disabled:opacity-50"
                aria-label="Send"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
