// Explicit foreground-only, bounded capture. The app owns this controller's lifetime.
export class StrumMicrophone {
 constructor({onState,onTake,mediaDevices=navigator.mediaDevices,Context=window.AudioContext,WorkletNode=window.AudioWorkletNode}) {
  Object.assign(this,{onState,onTake,mediaDevices,Context,WorkletNode});this.token=0;this.active=false;this.resources=null;
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&this.active)this.cancel('Detection cancelled because the page left the foreground. Microphone off.');});
  window.addEventListener('pagehide',()=>this.cancel());
 }
 state(phase,message){this.onState({phase,message});}
 async release(resource){
  if(!resource)return;
  if(resource.stream)resource.stream.getTracks().forEach(track=>{track.onended=null;track.stop();});
  for(const node of [resource.input,resource.node,resource.mute]){try{node?.disconnect();}catch{}}
  resource.node?.port.close();
  if(resource.context){resource.context.onstatechange=null;if(resource.context.state!=='closed')try{await resource.context.close();}catch{}}
 }
 async start(){
  if(this.active)return;
  if(!this.mediaDevices?.getUserMedia||!this.Context||!this.WorkletNode){this.state('idle','Microphone capture is unavailable. Try Safari or choose a WAV.');return;}
  const token=++this.token;this.active=true;this.state('requesting','Waiting for microphone permission…');
  const resource={};this.resources=resource;
  try{
   resource.stream=await this.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false});
   if(token!==this.token||document.hidden){await this.release(resource);return;}
   resource.context=new this.Context({sampleRate:48000});
   await resource.context.audioWorklet.addModule('/capture-worklet.js');await resource.context.resume();
   if(token!==this.token||document.hidden){await this.release(resource);return;}
   if(resource.context.state!=='running')throw Error('Microphone audio could not start. Retry or use Safari.');
   resource.node=new this.WorkletNode(resource.context,'baglama-capture',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1],channelCount:1,channelCountMode:'explicit',processorOptions:{durationSeconds:5}});
   resource.input=resource.context.createMediaStreamSource(resource.stream);resource.mute=resource.context.createGain();resource.mute.gain.value=0;
   resource.input.connect(resource.node);resource.node.connect(resource.mute);resource.mute.connect(resource.context.destination);
   resource.stream.getTracks().forEach(track=>track.onended=()=>{if(token===this.token)this.cancel('Microphone interrupted. Try again. Microphone off.');});
   resource.context.onstatechange=()=>{if(token===this.token&&resource.context.state==='suspended')this.cancel('Recording interrupted. Try again. Microphone off.');};
   this.state('listening','Microphone on · strum all open courses now. Finishes automatically after 5 seconds.');
   this.timer=setTimeout(()=>this.finish(),5000);
  }catch(error){
   await this.release(resource);
   if(token===this.token){this.resources=null;this.active=false;this.state('idle','Could not use microphone: '+error.message+' Microphone off. Retry or choose a WAV.');}
  }
 }
 async finish(){
  const resource=this.resources;if(!this.active||!resource?.node||this.finishing)return;
  this.finishing=true;clearTimeout(this.timer);const token=this.token;this.state('stopping','Preparing detection… Microphone off.');
  resource.stream.getTracks().forEach(track=>{track.onended=null;track.stop();});resource.context.onstatechange=null;
  let timeout;
  try{
   const data=await Promise.race([new Promise(resolve=>{resource.node.port.onmessage=e=>resolve(e.data);resource.node.port.postMessage('stop');}),new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Microphone buffer timed out. Please try again.')),1500);})]);
   if(token!==this.token)return;
   const samples=new Float32Array(data.samples).slice(0,Math.min(data.count,Math.floor(data.rate*5)));
   if(samples.length<data.rate*.4)throw Error('The recording was too short. Strum again.');
   await this.release(resource);
   if(token!==this.token)return;
   this.resources=null;this.active=false;this.finishing=false;this.state('idle','Microphone off. Analyzing your strum…');
   await this.onTake({samples,rate:data.rate,source:'microphone'});
  }catch(error){if(token===this.token){await this.release(resource);this.resources=null;this.active=false;this.finishing=false;this.state('idle',error.message+' Microphone off.');}}
  finally{clearTimeout(timeout);if(token===this.token)this.finishing=false;}
 }
 cancel(message='Detection cancelled. Microphone off.'){
  ++this.token;clearTimeout(this.timer);const resource=this.resources;this.resources=null;this.active=false;this.finishing=false;
  // Stop hardware synchronously, including while worklet initialization is pending.
  resource?.stream?.getTracks().forEach(track=>{track.onended=null;track.stop();});
  void this.release(resource);this.state('idle',message);
 }
}
