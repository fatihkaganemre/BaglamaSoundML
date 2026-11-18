// The audio callback only copies into a preallocated, bounded ten-second buffer.
// Transfer happens in the stop-message handler, outside process().
class CaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(); const requested=options?.processorOptions?.durationSeconds ?? 10;
    const seconds=Number.isFinite(requested)&&requested>=.4&&requested<=10?requested:10;
    this.samples = new Float32Array(Math.ceil(sampleRate * seconds)); this.count = 0; this.active = true;
    this.port.onmessage = event => {
      if (event.data === 'stop') {
        this.active = false;
        this.port.postMessage({ samples: this.samples.buffer, count: this.count, rate: sampleRate }, [this.samples.buffer]);
      } else if (event.data === 'cancel') { this.active = false; }
    };
  }
  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (this.active && input) {
      const count = Math.min(input.length, this.samples.length - this.count);
      for (let index = 0; index < count; index++) this.samples[this.count + index] = input[index];
      this.count += count;
    }
    return true;
  }
}
registerProcessor('baglama-capture', CaptureProcessor);
