/**
 * audio-capture-worklet.js
 * --------------------------
 * AudioWorkletProcessor that downsamples the mic's native sample rate to
 * 16-bit PCM16 @16kHz (via linear interpolation) and posts ~200ms chunks
 * back to the main thread as ArrayBuffers -- the exact format
 * backend/services/voice_session_service.py expects for
 * send_realtime_input(audio=Blob(mime_type="audio/pcm;rate=16000")).
 *
 * Runs on the audio rendering thread, so it must stay allocation-light per
 * process() call; the outbound chunk buffer is only built when a full
 * chunk's worth of samples is ready.
 */

class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = options && options.processorOptions ? options.processorOptions : {};
    this.targetRate = opts.targetSampleRate || 16000;
    // `sampleRate` is a global in AudioWorkletGlobalScope = the AudioContext's rate.
    this.ratio = sampleRate / this.targetRate;
    this.chunkSize = Math.floor(this.targetRate * 0.2); // ~200ms per chunk

    this.leftover = new Float32Array(0);
    this.pos = 0; // fractional read cursor into `leftover`, in input-sample units
    this.outChunk = [];
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;
    const incoming = input[0];

    const combined = new Float32Array(this.leftover.length + incoming.length);
    combined.set(this.leftover, 0);
    combined.set(incoming, this.leftover.length);

    while (this.pos + 1 < combined.length) {
      const i0 = Math.floor(this.pos);
      const frac = this.pos - i0;
      const s0 = combined[i0];
      const s1 = combined[i0 + 1];
      this.outChunk.push(s0 + (s1 - s0) * frac);
      this.pos += this.ratio;

      if (this.outChunk.length >= this.chunkSize) {
        this._flush();
      }
    }

    const consumedWhole = Math.floor(this.pos);
    this.leftover = combined.slice(consumedWhole);
    this.pos -= consumedWhole;

    return true;
  }

  _flush() {
    const samples = this.outChunk;
    this.outChunk = [];

    const pcm16 = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
  }
}

registerProcessor("audio-capture-processor", AudioCaptureProcessor);
