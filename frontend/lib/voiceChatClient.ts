/**
 * lib/voiceChatClient.ts
 * ------------------------
 * Thin WebSocket wrapper around the backend's voice assistant endpoint
 * (backend/app/api/voice_chat.py). Owned by AgentSidebar; connects directly
 * to the FastAPI backend (not proxied through a Next.js API route, since
 * Next's route handlers don't support persistent WebSocket proxying) --
 * same direct-to-backend precedent already used by app/gitbook/page.tsx.
 *
 * See the voice-assistant plan's "WebSocket protocol" section for the exact
 * message shapes this mirrors.
 */

export type VoiceEvent =
  | { type: "ready" }
  | { type: "partial_transcript"; role: "user"; text: string }
  | { type: "assistant_text_delta"; text: string }
  | { type: "assistant_audio_chunk"; data: string }
  | { type: "assistant_turn_complete" }
  | {
      type: "proposal";
      proposal_id: string;
      summary: string;
      rationale: string;
      diff: { before: string; after: string };
    }
  | {
      type: "proposal_applied";
      proposal_id: string;
      new_content: string;
      previous_content: string;
    }
  | { type: "proposal_rejected"; proposal_id: string }
  | { type: "error"; message: string }
  | { type: "closed"; reason?: string };

function backendWsBase(): string {
  const httpBase =
    process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
  return httpBase.replace(/^http/, "ws").replace(/\/$/, "");
}

export class VoiceChatClient {
  private ws: WebSocket | null = null;
  private listeners = new Set<(event: VoiceEvent) => void>();

  connect(params: { documentId: string; repositoryName: string }): Promise<void> {
    return new Promise((resolve, reject) => {
      const url =
        `${backendWsBase()}/api/voice-chat` +
        `?document_id=${encodeURIComponent(params.documentId)}` +
        `&repository_name=${encodeURIComponent(params.repositoryName)}`;

      const ws = new WebSocket(url);
      this.ws = ws;

      let settled = false;
      ws.onopen = () => {
        settled = true;
        resolve();
      };
      ws.onerror = () => {
        if (!settled) {
          settled = true;
          reject(new Error("Could not connect to the voice assistant."));
        }
      };
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as VoiceEvent;
          this.listeners.forEach((cb) => cb(data));
        } catch {
          // Ignore malformed frames rather than crashing the session.
        }
      };
      ws.onclose = (ev) => {
        this.listeners.forEach((cb) => cb({ type: "closed", reason: ev.reason || undefined }));
      };
    });
  }

  onEvent(cb: (event: VoiceEvent) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  private send(msg: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  sendText(text: string): void {
    this.send({ type: "user_text", text });
  }

  startAudioTurn(): void {
    this.send({ type: "audio_start" });
  }

  sendAudioChunk(base64Pcm16: string): void {
    this.send({ type: "audio_chunk", data: base64Pcm16 });
  }

  endAudioTurn(): void {
    this.send({ type: "audio_end" });
  }

  approveProposal(proposalId: string): void {
    this.send({ type: "approve_proposal", proposal_id: proposalId });
  }

  rejectProposal(proposalId: string, feedback?: string): void {
    this.send({ type: "reject_proposal", proposal_id: proposalId, feedback: feedback || "" });
  }

  close(): void {
    this.send({ type: "end_session" });
    this.ws?.close();
    this.ws = null;
    this.listeners.clear();
  }
}
