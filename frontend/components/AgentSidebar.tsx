"use client";

import { useCallback, useEffect, useRef, useState, KeyboardEvent, MouseEvent as ReactMouseEvent } from "react";
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
const DEFAULT_SIDEBAR_WIDTH = 420;
const MIN_SIDEBAR_WIDTH = 320;
const MAX_SIDEBAR_WIDTH = 800;
const SIDEBAR_WIDTH_STORAGE_KEY = "docubear_sidebar_width";

function clampSidebarWidth(width: number): number {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, width));
}

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
  const [hasConnectedOnce, setHasConnectedOnce] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [assistantSpeaking, setAssistantSpeaking] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);

  const scrollRef = useRef<HTMLDivElement>(null);
  const resizingRef = useRef(false);
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
  // Resolves/rejects once the backend confirms the Gemini Live session is
  // actually ready, so a lazily-triggered connect (first mic click or first
  // typed message) can be awaited instead of racing audio/text against a
  // socket that's merely open but not yet backed by a live session.
  const readyWaiterRef = useRef<{ resolve: () => void; reject: (err: Error) => void } | null>(null);

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

  // Restore a previously dragged width once mounted (avoids touching
  // localStorage during server-side rendering).
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
      const parsed = raw ? Number(raw) : NaN;
      if (Number.isFinite(parsed)) setSidebarWidth(clampSidebarWidth(parsed));
    } catch {
      // Storage unavailable -- default width still works.
    }
  }, []);

  // Drag-to-resize: the handle's onMouseDown just arms resizingRef; the
  // actual width tracking lives on window listeners so dragging keeps
  // working even if the cursor leaves the narrow handle strip mid-drag.
  useEffect(() => {
    function handleMouseMove(e: MouseEvent) {
      if (!resizingRef.current) return;
      setSidebarWidth(clampSidebarWidth(window.innerWidth - e.clientX));
    }
    function handleMouseUp() {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setSidebarWidth((width) => {
        try {
          window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(width));
        } catch {
          // Storage unavailable -- resize still works for this session.
        }
        return width;
      });
    }
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const handleResizeStart = useCallback((e: ReactMouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

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
    setIsRecording(false);
    setAssistantSpeaking(false);
  }, []);

  const handleVoiceEvent = useCallback(
    (event: VoiceEvent) => {
      switch (event.type) {
        case "ready": {
          setConnecting(false);
          setSessionActive(true);
          setHasConnectedOnce(true);
          readyWaiterRef.current?.resolve();
          readyWaiterRef.current = null;
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
          readyWaiterRef.current?.reject(new Error(event.message));
          readyWaiterRef.current = null;
          break;
        }
        case "closed": {
          readyWaiterRef.current?.reject(new Error(event.reason || "Connection closed"));
          readyWaiterRef.current = null;
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
      // The socket being open doesn't mean the Gemini Live session behind
      // it is ready yet -- wait for the backend's "ready" event so callers
      // (first mic click, first typed message) never send into a session
      // that hasn't actually started.
      await new Promise<void>((resolve, reject) => {
        readyWaiterRef.current = { resolve, reject };
      });
    } catch (err) {
      setConnecting(false);
      setError(err instanceof Error ? err.message : "Could not connect to the assistant.");
      clientRef.current?.close();
      clientRef.current = null;
      playerRef.current?.close();
      playerRef.current = null;
    } finally {
      readyWaiterRef.current = null;
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

  // Nothing connects just because a document is open -- the assistant
  // (mic capture, and the Gemini Live session backing it) only starts once
  // the user explicitly acts: clicking the mic button or sending a typed
  // message. Switching to a different document still tears down and resets
  // whatever session/conversation was scoped to the previous one, but does
  // not implicitly start a new one for the document now open.
  useEffect(() => {
    const key = repositoryName && documentId ? `${repositoryName}::${documentId}` : null;
    const switchedDocument = connectedKeyRef.current !== null && connectedKeyRef.current !== key;
    if (switchedDocument) {
      endSession();
      setHasConnectedOnce(false);
      setSessionItems([]);
    }
    connectedKeyRef.current = key;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repositoryName, documentId]);

  // ------------------------------------------------------------------
  // Voice recording -- click to start, click again (or the Stop control) to
  // end. Lazily connects the session on first use so nothing runs until the
  // user actually presses the button.
  // ------------------------------------------------------------------

  // Guarded on captureRef (a ref, always current) rather than the isRecording
  // state, so it's safe to call from anywhere -- including the silence-based
  // auto-stop callback below, which fires from inside a closure created back
  // when recording started and can't be relied on to see fresh state.
  const stopRecording = useCallback(() => {
    if (!captureRef.current) return;
    captureRef.current.stop();
    captureRef.current = null;
    clientRef.current?.endAudioTurn();
    setIsRecording(false);
  }, []);

  const startRecording = useCallback(async () => {
    if (isRecording || connecting) return;
    setError(null);
    if (!clientRef.current) {
      await startSession();
    }
    if (!clientRef.current) return; // connect failed; error already surfaced
    setIsRecording(true);
    lastInputModeRef.current = "voice";
    playerRef.current?.stopAndClear(); // barge-in: stop assistant audio if it's still playing
    suppressAudioRef.current = false; // this new turn's reply should still be heard
    setAssistantSpeaking(false);
    clientRef.current.startAudioTurn();
    const capture = new PcmAudioCapture();
    captureRef.current = capture;
    try {
      // onAutoStop: ends the turn on its own once the user stops talking, so
      // one click both starts and (normally) finishes a turn -- listening
      // stops right there rather than staying on for the rest of the reply.
      // Clicking the mic button again still ends it immediately by hand.
      await capture.start((chunk) => clientRef.current?.sendAudioChunk(chunk), () => stopRecording());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access failed.");
      setIsRecording(false);
      captureRef.current = null;
    }
  }, [isRecording, connecting, startSession, stopRecording]);

  const handleMicButtonClick = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

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
          style={{ width: sidebarWidth }}
          className="fixed right-0 top-0 z-50 flex h-screen max-w-[95vw] flex-col border-l border-border bg-surface shadow-2xl"
        >
          {/* Drag handle -- grab anywhere along the left edge to resize. */}
          <div
            onMouseDown={handleResizeStart}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize assistant panel"
            title="Drag to resize"
            className="absolute left-0 top-0 z-10 h-full w-1.5 -translate-x-1/2 cursor-col-resize touch-none hover:bg-teal/40 active:bg-teal/60 transition-colors"
          />

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

          {/* Assistant session status -- only rendered once a connection has
              actually been requested (by clicking the mic or sending a
              message), since nothing connects just because a document is
              open. */}
          {documentId && (connecting || sessionActive || hasConnectedOnce) && (
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
                  ? "Ask me anything about this repository, or ask for a change to this document — I'll draft it and wait for your approval. Click the mic button to talk instead of typing, then click it again to finish."
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
          <div className="relative border-t border-border p-3 shrink-0">
            {/* Small floating "live" badge while recording -- just a status
                indicator, not a button; clicking the mic button again ends
                the recording. The only "Stop" control in the whole panel is
                the one below, which silences the assistant's voice reply
                (text keeps streaming in either case). */}
            {isRecording && (
              <div className="absolute -top-8 right-3 flex items-center gap-1.5 rounded-full bg-rose-600 text-white pl-2 pr-2.5 py-1 shadow-lg">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-white" />
                </span>
                <span className="text-[9px] font-bold uppercase tracking-wider">Listening</span>
              </div>
            )}
            {assistantSpeaking && (
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
                  onClick={handleMicButtonClick}
                  disabled={connecting && !isRecording}
                  title={isRecording ? "Click to finish recording" : connecting ? "Connecting..." : "Start recording"}
                  className={`shrink-0 rounded-full p-2.5 transition-all select-none disabled:opacity-40 disabled:cursor-not-allowed ${
                    isRecording ? "bg-rose-600 text-white animate-pulse" : "bg-text text-white hover:bg-accent"
                  }`}
                  aria-label={isRecording ? "Finish recording" : "Start recording"}
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
