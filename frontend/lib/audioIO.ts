/**
 * lib/audioIO.ts
 * ----------------
 * Browser-side audio plumbing for the voice assistant:
 *  - PcmAudioCapture: mic -> AudioWorklet (downsamples to 16-bit PCM16 @16kHz)
 *    -> base64 chunks, matching what backend/services/voice_session_service.py
 *    expects for send_realtime_input.
 *  - PcmAudioPlayer: queues 24kHz PCM16 chunks (what Gemini Live returns) into
 *    a second AudioContext for gapless-ish playback via scheduled
 *    AudioBufferSourceNodes (a plain <audio> tag can't play raw PCM).
 *
 * AudioWorklet is used for capture instead of the deprecated
 * ScriptProcessorNode (main-thread jank) or MediaRecorder (which only
 * produces compressed Opus/WebM, not raw PCM).
 */

const CAPTURE_TARGET_SAMPLE_RATE = 16000;
const PLAYBACK_SAMPLE_RATE = 24000;
const CAPTURE_WORKLET_URL = "/audio-capture-worklet.js";
const CAPTURE_WORKLET_NAME = "audio-capture-processor";

// End-of-turn silence detection: once the user has said *something* above
// SPEECH_RMS_THRESHOLD, a continuous SILENCE_HANG_MS stretch below it is
// treated as "done talking" and auto-ends the recording -- so a single mic
// click both starts and (normally) ends a turn, no second click required.
// Heuristic, not a real VAD; tuned loosely against getUserMedia's own
// echoCancellation/noiseSuppression already cleaning up the signal.
const SPEECH_RMS_THRESHOLD = 500;
const SILENCE_HANG_MS = 1200;

function bufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function base64ToInt16Array(base64: string): Int16Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}

export class PcmAudioCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private hasDetectedSpeech = false;
  private silenceSinceMs: number | null = null;

  /**
   * @param onAutoStop Called at most once, the moment sustained silence
   * follows detected speech -- the caller should stop() the capture (and
   * end the turn) in response. Recording never auto-stops before any
   * speech has been heard, so pausing to think before talking is safe.
   */
  async start(onChunk: (base64Pcm16: string) => void, onAutoStop?: () => void): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    this.ctx = new AudioContext();
    await this.ctx.audioWorklet.addModule(CAPTURE_WORKLET_URL);

    this.hasDetectedSpeech = false;
    this.silenceSinceMs = null;

    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.worklet = new AudioWorkletNode(this.ctx, CAPTURE_WORKLET_NAME, {
      processorOptions: {
        inputSampleRate: this.ctx.sampleRate,
        targetSampleRate: CAPTURE_TARGET_SAMPLE_RATE,
      },
    });
    this.worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      if (onAutoStop) this._trackSilence(event.data, onAutoStop);
      onChunk(bufferToBase64(event.data));
    };

    // Deliberately not connected to ctx.destination -- we don't want to
    // hear our own microphone played back.
    this.source.connect(this.worklet);
  }

  private _trackSilence(buf: ArrayBuffer, onAutoStop: () => void): void {
    const samples = new Int16Array(buf);
    let sumSquares = 0;
    for (let i = 0; i < samples.length; i++) sumSquares += samples[i] * samples[i];
    const rms = samples.length ? Math.sqrt(sumSquares / samples.length) : 0;

    if (rms >= SPEECH_RMS_THRESHOLD) {
      this.hasDetectedSpeech = true;
      this.silenceSinceMs = null;
      return;
    }
    if (!this.hasDetectedSpeech) return; // still waiting for the user to start talking

    const now = performance.now();
    if (this.silenceSinceMs === null) {
      this.silenceSinceMs = now;
    } else if (now - this.silenceSinceMs >= SILENCE_HANG_MS) {
      this.silenceSinceMs = null; // one-shot -- stop() tears the worklet down right after
      onAutoStop();
    }
  }

  stop(): void {
    this.worklet?.port.close();
    this.worklet?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.ctx?.close().catch(() => {});
    this.worklet = null;
    this.source = null;
    this.stream = null;
    this.ctx = null;
  }
}

export class PcmAudioPlayer {
  private ctx: AudioContext;
  private nextStartTime: number;
  private activeSources: AudioBufferSourceNode[] = [];

  constructor() {
    this.ctx = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE });
    this.nextStartTime = this.ctx.currentTime;
  }

  enqueuePcm16(base64: string): void {
    const pcm16 = base64ToInt16Array(base64);
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i++) float32[i] = pcm16[i] / 0x8000;

    const audioBuffer = this.ctx.createBuffer(1, float32.length, PLAYBACK_SAMPLE_RATE);
    audioBuffer.copyToChannel(float32, 0);

    const source = this.ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.ctx.destination);
    source.onended = () => {
      this.activeSources = this.activeSources.filter((s) => s !== source);
    };

    const startAt = Math.max(this.nextStartTime, this.ctx.currentTime);
    source.start(startAt);
    this.nextStartTime = startAt + audioBuffer.duration;
    this.activeSources.push(source);
  }

  /** Barge-in: stop everything queued/playing and reset the schedule. */
  stopAndClear(): void {
    for (const source of this.activeSources) {
      try {
        source.stop();
      } catch {
        // Already stopped/ended -- fine.
      }
    }
    this.activeSources = [];
    this.nextStartTime = this.ctx.currentTime;
  }

  close(): void {
    this.stopAndClear();
    this.ctx.close().catch(() => {});
  }
}
