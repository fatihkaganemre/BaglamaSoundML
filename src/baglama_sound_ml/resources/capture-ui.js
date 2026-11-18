import {drawWave,trimBounds,trimmedTake} from '/lab-audio.js';
const $=id=>document.getElementById(id);
export class SampleEditor {
 constructor({api,audio,notify,saved}) {
 Object.assign(this,{api,audio,notify,saved}); this.take=null;this.sequence=0;
 $('playTake').onclick=()=>this.guard(()=>{const s=this.selection();return audio.playSamples(s.samples,this.take.rate,'Sample selection');});
 $('playFullTake').onclick=()=>this.guard(()=>audio.playSamples(this.take.samples,this.take.rate,'Original sample'));
 for(const id of ['trimStart','trimEnd'])$(id).addEventListener('input',()=>this.trimSeconds());
 $('trimStartRange').addEventListener('input',()=>this.setTrim(Number($('trimStartRange').value),this.trim.endFrame));
 $('trimEndRange').addEventListener('input',()=>this.setTrim(this.trim.startFrame,Number($('trimEndRange').value)));
 $('resetTrim').onclick=()=>this.resetTrim();$('discardTake').onclick=()=>this.close();$('saveTake').onclick=()=>this.save();
 }
 async guard(action){try{await action();}catch(e){this.notify(e.message,true);}}
 async open(row,title){
 const sequence=++this.sequence;this.audio.stop();this.notify('Loading original waveform…');
 const data=await this.api('/api/samples/'+row.id+'/original');if(sequence!==this.sequence)return;
 const bytes=Uint8Array.from(atob(data.audio),c=>c.charCodeAt(0));
 this.take={samples:new Float32Array(bytes.buffer),rate:data.sampleRate,id:row.id};
 $('editTitle').textContent=title;$('review').hidden=false;$('reviewControls').disabled=false;
 $('reviewDescription').textContent='Original: '+(this.take.samples.length/this.take.rate).toFixed(3)+' seconds · '+this.take.rate+' Hz';
 this.setTrim(data.startFrame,data.endFrame);$('review').scrollIntoView({block:'start'});this.notify('Edit the selection, preview, then save trim.');
 }
 close(){++this.sequence;this.audio.stop();this.take=null;$('review').hidden=true;}
 async save(){if(!this.take)return;await this.guard(async()=>{
 this.selection();$('reviewControls').disabled=true;
 try{await this.api('/api/samples/'+this.take.id+'/trim',{startFrame:this.trim.startFrame,endFrame:this.trim.endFrame});await this.saved();this.notify('Trim saved. Playback and ZIP export use this selection. The original remains available.');}
 finally{$('reviewControls').disabled=false;}
 });}
  resetTrim(){
    if(!this.take)return;
    this.setTrim(0,this.take.samples.length);
  }
  trimSeconds(){
    if(!this.take)return;
    const start=$('trimStart').value,end=$('trimEnd').value;
    if(!start.trim()||!end.trim())return this.invalidTrim('Enter both the start and end times.');
    this.setTrim(Math.round(Number(start)*this.take.rate),Math.round(Number(end)*this.take.rate),false);
  }
  invalidTrim(message){
    this.audio.stop();this.trimInvalid=true;
    $('trimError').textContent=message;$('playTake').disabled=true;$('saveTake').disabled=true;
  }
  setTrim(startFrame,endFrame,syncFields=true){
    if(!this.take)return;
    this.audio.stop();
    try{
      this.trim=trimBounds(this.take.samples.length,this.take.rate,startFrame,endFrame);
      this.trimInvalid=false;$('trimError').textContent='';$('playTake').disabled=false;$('saveTake').disabled=false;
      const total=this.take.samples.length,rate=this.take.rate,minFrames=Math.ceil(rate*.2);
      const start=startFrame/rate,end=endFrame/rate;
      for(const id of ['trimStart','trimEnd']){$(id).min='0';$(id).max=(total/rate).toFixed(6);}
      if(syncFields){$('trimStart').value=start.toFixed(6);$('trimEnd').value=end.toFixed(6);}
      $('trimStartRange').min='0';$('trimStartRange').max=String(endFrame-minFrames);$('trimStartRange').value=String(startFrame);
      $('trimEndRange').min=String(startFrame+minFrames);$('trimEndRange').max=String(total);$('trimEndRange').value=String(endFrame);
      $('trimStartRange').setAttribute('aria-valuetext',start.toFixed(3)+' seconds');
      $('trimEndRange').setAttribute('aria-valuetext',end.toFixed(3)+' seconds');
      $('selectionDescription').textContent='Keep '+start.toFixed(3)+'–'+end.toFixed(3)+' s · '+this.trim.duration.toFixed(3)+' seconds selected. Only this portion will be saved.';
      this.drawTrim();
    }catch(error){this.invalidTrim(error.message);}
  }
  drawTrim(){
    const canvas=$('recordWave');drawWave(canvas,this.take.samples);
    const ctx=canvas.getContext('2d'),width=canvas.width,height=canvas.height,total=this.take.samples.length;
    const left=this.trim.startFrame/total*width,right=this.trim.endFrame/total*width;
    ctx.fillStyle='rgba(16,40,42,.82)';ctx.fillRect(0,0,left,height);ctx.fillRect(right,0,width-right,height);
    ctx.fillStyle='rgba(239,207,145,.10)';ctx.fillRect(left,0,right-left,height);
    ctx.strokeStyle='#efcf91';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(left,0);ctx.lineTo(left,height);ctx.moveTo(right,0);ctx.lineTo(right,height);ctx.stroke();
    canvas.setAttribute('aria-label','Recorded waveform. Selected '+(this.trim.startFrame/this.take.rate).toFixed(3)+' to '+(this.trim.endFrame/this.take.rate).toFixed(3)+' seconds.');
  }
  selection(){
    if(!this.take||this.trimInvalid||!this.trim)throw Error('Choose a valid trim range first.');
    return trimmedTake(this.take.samples,this.take.rate,this.trim.startFrame,this.trim.endFrame);
  }

}
