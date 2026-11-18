const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../src/baglama_sound_ml/resources/strum-microphone.js'),'utf8');
const moduleURL='data:text/javascript;base64,'+Buffer.from(source).toString('base64');
function environment(){
 const listeners={};global.document={hidden:false,addEventListener:(event,fn)=>listeners[event]=fn};global.window={addEventListener:(event,fn)=>listeners[event]=fn};
 const track={stopped:false,stop(){this.stopped=true;}};const stream={getTracks:()=>[track]};let context;
 class Context{constructor(){context=this;this.state='running';this.audioWorklet={addModule:async()=>{}};this.destination={};}async resume(){}async close(){this.state='closed';}createMediaStreamSource(){return {connect(){},disconnect(){}};}createGain(){return {gain:{value:1},connect(){},disconnect(){}};}}
 class Worklet{constructor(_context,_name,options){this.options=options;this.port={close(){},postMessage:message=>{if(message==='stop')queueMicrotask(()=>this.port.onmessage({data:{samples:new Float32Array(264000).fill(.1).buffer,count:264000,rate:48000}}));}};}connect(){}disconnect(){}}
 return {listeners,track,stream,Context,Worklet,get context(){return context;}};
}
test('finish stops hardware before delivering bounded PCM to analysis',async()=>{
 const e=environment();const {StrumMicrophone}=await import(moduleURL);let received,options;
 const mic=new StrumMicrophone({onState(){},onTake:value=>{assert.equal(e.track.stopped,true);assert.equal(e.context.state,'closed');received=value;},mediaDevices:{getUserMedia:async value=>{options=value;return e.stream;}},Context:e.Context,WorkletNode:e.Worklet});
 await mic.start();assert.equal(mic.active,true);assert.equal(options.audio.echoCancellation,false);assert.equal(mic.resources.node.options.processorOptions.durationSeconds,5);
 await mic.finish();assert.equal(received.samples.length,240000);assert.equal(received.source,'microphone');assert.equal(mic.active,false);
});
test('cancel during permission prompt discards a late stream without analysis',async()=>{
 const e=environment();const {StrumMicrophone}=await import(moduleURL);let resolve,analyzed=false;
 const mic=new StrumMicrophone({onState(){},onTake(){analyzed=true;},mediaDevices:{getUserMedia:()=>new Promise(r=>resolve=r)},Context:e.Context,WorkletNode:e.Worklet});
 const pending=mic.start();mic.cancel();resolve(e.stream);await pending;assert.equal(e.track.stopped,true);assert.equal(analyzed,false);assert.equal(mic.active,false);
});
test('backgrounding cancels foreground capture and permission denial recovers',async()=>{
 const e=environment();const {StrumMicrophone}=await import(moduleURL);let analyzed=false,message;
 const mic=new StrumMicrophone({onState:value=>message=value.message,onTake(){analyzed=true;},mediaDevices:{getUserMedia:async()=>e.stream},Context:e.Context,WorkletNode:e.Worklet});
 await mic.start();document.hidden=true;e.listeners.visibilitychange();assert.equal(e.track.stopped,true);assert.equal(mic.active,false);assert.equal(analyzed,false);
 document.hidden=false;const denied=new StrumMicrophone({onState:value=>message=value.message,onTake(){},mediaDevices:{getUserMedia:async()=>{throw Error('Permission denied');}},Context:e.Context,WorkletNode:e.Worklet});
 await denied.start();assert.equal(denied.active,false);assert.match(message,/Permission denied/);
});
