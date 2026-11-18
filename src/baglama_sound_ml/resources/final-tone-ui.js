import {FinalToneExamples} from '/final-tone-examples.js';
import {StrumMicrophone} from '/strum-microphone.js';
import {base64,drawWave} from '/lab-audio.js';
export function initFinalTone({api,audio,notify,catalog}) {
 const $=id=>document.getElementById(id);let take=null,capture=null,busy=false,examples=null;
 function lock(value){busy=value;const locked=busy||!!capture?.active;$('strumCaseFields').disabled=locked;$('strumCaseManagement').disabled=locked;$('strumControls').disabled=busy||!!capture?.active;$('startStrumMic').disabled=busy||!!capture?.active;$('cancelStrumMic').disabled=!capture?.active;}
 function showTake(value,description){examples?.candidate(null);take=value;drawWave($('strumWave'),value.samples);$('strumFileDescription').textContent=description;$('playStrum').disabled=false;$('analyzeStrum').disabled=false;}
 function result(r){
  $('strumResult').textContent=r.status==='detected'?(r.tuningStatus==='inTune'?'Final tone: ':'Possible final tone: ')+r.finalTone.name:'Insufficient evidence · strum again';
  $('strumExplanation').textContent=r.message+' Evidence is not a calibrated probability.';
  $('strumCourses').replaceChildren();
  for(const c of r.courses){const li=document.createElement('li');li.textContent=({ust:'Upper / Üst',orta:'Middle / Orta',alt:'Lower / Alt'})[c.course]+': '+c.note+' · '+c.frequencyHertz.toFixed(2)+' Hz · '+(c.centsFromNote>=0?'+':'')+c.centsFromNote.toFixed(1)+'¢ · '+(c.inTune?'in tune':'needs tuning');$('strumCourses').append(li);}
  $('strumCandidates').textContent='Candidate scores: '+r.candidates.map(c=>c.name+' '+c.score.toFixed(2)).join(' · ');
 }
 async function analyze(demo=false){
  lock(true);audio.stop();examples?.candidate(null);
  try{
   if(!demo&&!take)throw Error('Choose a strum WAV first.');
   $('strumResult').textContent='Analyzing locally…';
   const body={referenceHertz:Number($('strumReference').value),demo};
   if(!demo)Object.assign(body,{sampleRate:take.rate,audio:base64(new Uint8Array(take.samples.buffer))});
   const detected=await api('/api/final-tone',body);result(detected);if(!demo)examples.candidate({...take,reference:body.referenceHertz});$('strumResultSource').textContent=demo?'Source: synthetic La / A example (not the selected WAV)':(take.source==='microphone'?'Source: microphone strum · microphone off':'Source: selected strum WAV');notify(demo?'Synthetic demonstration only; not a real-instrument accuracy test.':'Strum analyzed locally. Review the result, then label it below to save an evaluation case.');
  }catch(e){$('strumResult').textContent='Could not analyze';$('strumExplanation').textContent=e.message;$('strumCourses').replaceChildren();$('strumCandidates').textContent='';notify(e.message,true);}
  finally{lock(false);}
 }
 $('chooseStrum').onclick=()=>$('strumFile').click();
 $('strumFile').onchange=async event=>{
  const file=event.target.files[0];event.target.value='';if(!file)return;
  audio.stop();examples?.candidate(null);take=null;$('strumResultSource').textContent='';$('strumCourses').replaceChildren();$('strumCandidates').textContent='';$('strumExplanation').textContent='';$('strumFileDescription').textContent='No strum selected.';const canvas=$('strumWave');canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);$('playStrum').disabled=true;$('analyzeStrum').disabled=true;let context;
  lock(true);
  try{
   if(file.size>20*1024*1024)throw Error('Choose a WAV smaller than 20 MB.');
   context=new AudioContext();const buffer=await context.decodeAudioData(await file.arrayBuffer());
   if(buffer.duration<.4||buffer.duration>8)throw Error('Choose 0.4–8 seconds of open-string strum audio.');
   const samples=new Float32Array(buffer.length);
   for(let c=0;c<buffer.numberOfChannels;c++){const values=buffer.getChannelData(c);for(let i=0;i<samples.length;i++)samples[i]+=values[i]/buffer.numberOfChannels;}
   showTake({samples,rate:buffer.sampleRate,source:'WAV'},file.name+' · '+buffer.duration.toFixed(2)+' s · '+buffer.sampleRate+' Hz');
   $('playStrum').disabled=false;$('analyzeStrum').disabled=false;$('strumResult').textContent='Ready to analyze';$('strumExplanation').textContent='';$('strumCourses').replaceChildren();$('strumCandidates').textContent='';
  }catch(e){notify(e.message,true);$('strumResult').textContent=e.message;}
  finally{if(context)await context.close();lock(false);}
 };
 $('playStrum').onclick=()=>{if(take)audio.playSamples(take.samples,take.rate,'Unsaved strum').catch(e=>notify(e.message,true));};
 examples=new FinalToneExamples({api,audio,notify,lock,catalog});
 capture=new StrumMicrophone({onState:({phase,message})=>{$('strumMicStatus').textContent=message;lock(busy);},onTake:async value=>{showTake(value,'Microphone strum · '+(value.samples.length/value.rate).toFixed(2)+' s · not saved');await analyze();}});
 $('startStrumMic').onclick=()=>{
  if(!$('strumMicConsent').checked){$('strumMicStatus').textContent='Accept the local microphone explanation first.';return;}
  audio.stop();examples?.candidate(null);$('strumResultSource').textContent='';$('strumCourses').replaceChildren();$('strumCandidates').textContent='';$('strumExplanation').textContent='';$('strumResult').textContent='Waiting for a strum…';capture.start();
 };
 $('cancelStrumMic').onclick=()=>capture.cancel();
 $('strumMicConsent').onchange=()=>{if(!$('strumMicConsent').checked&&capture.active)capture.cancel('Capture consent withdrawn. Microphone off.');};
 $('analyzeStrum').onclick=()=>analyze();$('demoStrum').onclick=()=>analyze(true);
 return {leave(){if(capture.active)capture.cancel('Detection cancelled because you left the detector. Microphone off.');}};
}
