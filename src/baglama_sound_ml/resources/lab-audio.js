export class LabAudio {
  constructor(status) { this.status=status; this.context=null; this.source=null; this.sequence=0; }
  async enable() {
    const Context=window.AudioContext||window.webkitAudioContext;
    if(!Context) throw Error('Audio playback is unavailable in this browser. Open the local app in Safari.');
    this.context=this.context||new Context();
    await this.context.resume();
    if(this.context.state!=='running') throw Error('Audio is blocked. Click Play again or open this local page in Safari.');
  }
  stop() { this.sequence++; if(this.source){this.source.onended=null;try{this.source.stop();}catch{}this.source=null;} this.status('Playback stopped.'); }
  async playURL(url,label,waveform) {
    this.stop(); const sequence=this.sequence;
    await this.enable();
    const response=await fetch(url,{cache:'no-store'});
    if(!response.ok) throw Error('Could not load this local sound.');
    const buffer=await this.context.decodeAudioData(await response.arrayBuffer());
    if(sequence!==this.sequence) return false;
    if(waveform) drawWave(waveform,buffer.getChannelData(0));
    return this.playBuffer(buffer,label,sequence);
  }
  async playSamples(samples,rate,label) {
    this.stop();const sequence=this.sequence;await this.enable();
    if(sequence!==this.sequence)return false;
    const buffer=this.context.createBuffer(1,samples.length,rate);buffer.copyToChannel(samples,0);
    return this.playBuffer(buffer,label,sequence);
  }
  playBuffer(buffer,label,sequence) {
    const source=this.context.createBufferSource(); source.buffer=buffer;source.connect(this.context.destination);
    source.onended=()=>{if(sequence===this.sequence){this.source=null;this.status('Finished · '+label);}};
    this.source=source;source.start();this.status('Playing · '+label+' · audio enabled');return true;
  }
}
export function drawWave(canvas,samples){
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.strokeStyle='#efcf91';ctx.lineWidth=1.5;
  const step=Math.max(1,Math.floor(samples.length/canvas.width));let scale=0;
  for(let i=0;i<samples.length;i++)scale=Math.max(scale,Math.abs(samples[i]));scale=Math.max(scale,1e-6);
  ctx.beginPath();for(let x=0;x<canvas.width;x++){let peak=0;for(let i=x*step;i<Math.min((x+1)*step,samples.length);i++)peak=Math.max(peak,Math.abs(samples[i]));const h=peak/scale*canvas.height*.45;ctx.moveTo(x,canvas.height/2-h);ctx.lineTo(x,canvas.height/2+h);}ctx.stroke();
}
export function base64(bytes){let value='';for(let i=0;i<bytes.length;i+=16384)value+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(value);}

// Frame-based bounds keep preview and saved PCM aligned, including fractional durations.
export function trimBounds(frameCount, rate, startFrame, endFrame) {
  if (!Number.isInteger(frameCount) || frameCount < 1 || !Number.isFinite(rate) || rate < 8000 || rate > 192000 ||
      !Number.isInteger(startFrame) || !Number.isInteger(endFrame) || startFrame < 0 || endFrame > frameCount ||
      endFrame - startFrame < Math.ceil(rate * 0.2)) {
    throw Error('Select at least 0.20 seconds within the recorded take.');
  }
  return {startFrame, endFrame, duration: (endFrame - startFrame) / rate};
}

export function trimmedTake(samples, rate, startFrame, endFrame) {
  const bounds = trimBounds(samples.length, rate, startFrame, endFrame);
  return {...bounds, samples: samples.slice(startFrame, endFrame)};
}
