class TTSPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferQueue = [];
    this.readOffset = 0;
    this.samplesRemaining = 0;
    this.isPlaying = false;

    // Resampling from 24kHz to 48kHz (2x upsampling)
    this.inputSampleRate = 24000;
    this.outputSampleRate = sampleRate; // Browser's sample rate
    this.resampleRatio = this.outputSampleRate / this.inputSampleRate;
    this.samplePosition = 0;

    console.log('TTS Worklet - Input:', this.inputSampleRate, 'Output:', this.outputSampleRate, 'Ratio:', this.resampleRatio);

    // Listen for incoming messages
    this.port.onmessage = (event) => {
      // Check if this is a control message (object with a "type" property).
      if (event.data && typeof event.data === "object" && event.data.type === "clear") {
        // Clear the TTS buffer and reset playback state.
        this.bufferQueue = [];
        this.readOffset = 0;
        this.samplesRemaining = 0;
        this.isPlaying = false;
        this.samplePosition = 0;
        return;
      }

      // Otherwise assume it's a PCM chunk (e.g., an Int16Array)
      this.bufferQueue.push(event.data);
      this.samplesRemaining += event.data.length;
    };
  }

  process(inputs, outputs) {
    const outputChannel = outputs[0][0];

    if (this.samplesRemaining === 0) {
      outputChannel.fill(0);
      if (this.isPlaying) {
        this.isPlaying = false;
        this.port.postMessage({ type: 'ttsPlaybackStopped' });
      }
      return true;
    }

    if (!this.isPlaying) {
      this.isPlaying = true;
      this.port.postMessage({ type: 'ttsPlaybackStarted' });
    }

    // Resample from 24kHz to browser sample rate
    let outIdx = 0;
    while (outIdx < outputChannel.length && this.bufferQueue.length > 0) {
      const currentBuffer = this.bufferQueue[0];

      // Linear interpolation for resampling
      const inputIndex = Math.floor(this.samplePosition);
      const fraction = this.samplePosition - inputIndex;

      if (inputIndex + 1 < currentBuffer.length) {
        // Interpolate between two samples
        const sample1 = currentBuffer[inputIndex] / 32768;
        const sample2 = currentBuffer[inputIndex + 1] / 32768;
        const interpolated = sample1 + (sample2 - sample1) * fraction;
        outputChannel[outIdx++] = interpolated;
      } else if (inputIndex < currentBuffer.length) {
        // Last sample in buffer
        outputChannel[outIdx++] = currentBuffer[inputIndex] / 32768;
      }

      // Advance position by input sample rate ratio
      this.samplePosition += 1 / this.resampleRatio;

      // Move to next buffer when we've consumed this one
      if (Math.floor(this.samplePosition) >= currentBuffer.length) {
        this.samplesRemaining -= currentBuffer.length;
        this.bufferQueue.shift();
        this.samplePosition = 0;
      }
    }

    // Fill remaining with silence
    while (outIdx < outputChannel.length) {
      outputChannel[outIdx++] = 0;
    }

    return true;
  }
}

registerProcessor('tts-playback-processor', TTSPlaybackProcessor);
