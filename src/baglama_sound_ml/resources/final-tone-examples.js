import {StrumStringFields,noteNames as names} from '/strum-string-fields.js';
import {base64} from '/lab-audio.js';

export class FinalToneExamples {
 constructor({api,audio,notify,lock,catalog={instruments:[]}}){
  Object.assign(this,{api,audio,notify,lock});this.current=null;this.rows=[];
  const $=id=>document.getElementById(id);this.$=$;
  names.forEach((name,i)=>$('strumKnownTone').add(new Option(name,String(i))));this.stringFields=new StrumStringFields(catalog);
  $('strumSaveCase').onclick=()=>this.save();$('strumCaseTrash').onchange=()=>this.refresh().catch(e=>notify(e.message,true));
  $('strumCaseList').addEventListener('click',event=>{const button=event.target.closest('button[data-case-action]');if(!button)return;this.action(button).catch(e=>notify(e.message,true));});
  this.refresh().catch(e=>notify('Could not load strum test cases: '+e.message,true));
 }
 candidate(value){this.current=value;this.$('strumCaseForm').hidden=!value;this.$('strumCaseSubject').textContent=value?.savedId?'Editing saved test case '+value.savedId.slice(0,8):'Labeling the most recently analyzed real strum';if(value){this.$('strumKnownTone').value='';this.stringFields.reset();this.$('strumCaseNotes').value='';this.$('strumCaseConsent').checked=false;}}
 async save(){
  const $=this.$,c=this.current;if(!c)return;
  if(!$('strumCaseConsent').checked){this.notify('Confirm that this is a real strum and allow saving its audio locally.',true);return;}
  if($('strumKnownTone').value===''){this.notify('Choose the independently known final tone first.',true);return;}
  let labels;try{labels=this.stringFields.payload();}catch(e){this.notify(e.message,true);return;}
  this.lock(true);
  try{
   const result=await this.api('/api/final-tone-tests',{audio:base64(new Uint8Array(c.samples.buffer,c.samples.byteOffset,c.samples.byteLength)),sampleRate:c.rate,referenceHertz:c.reference,source:c.source,confirmedReal:true,expectedPitchClass:Number($('strumKnownTone').value),...labels,notes:$('strumCaseNotes').value});
   this.current.savedId=result.id;$('strumCaseTrash').value='0';await this.refresh();this.notify(result.duplicate?'Existing test case label updated; audio was not duplicated.':'Saved the real strum and your label as local evaluation data. Training is unchanged.');
  }catch(e){this.notify('Could not save test case: '+e.message+' Your strum is still available to retry.',true);}
  finally{this.lock(false);}
 }
 async refresh(){
  const $=this.$;this.rows=(await this.api('/api/final-tone-tests?trash='+$('strumCaseTrash').value)).cases;
  $('strumCaseCount').textContent=this.rows.length+' saved '+($('strumCaseTrash').value==='1'?'trashed ':'')+'test cases';$('strumCaseList').replaceChildren();if(!this.rows.length){$('strumCaseList').textContent='No saved test cases in this view.';return;}
  for(const row of this.rows){
   const article=document.createElement('article');article.className='list-row';const info=document.createElement('div');const title=document.createElement('h4');title.textContent='Known final tone: '+names[row.expected];
   const detail=document.createElement('p');const guess=row.prediction.finalTone?.name||'Insufficient evidence';const details=row.instrumentDetails||{};const instrument=this.stringFields.catalog.instruments.find(i=>i.id===details.instrumentID);detail.textContent=(instrument?instrument.title+' · ':'Baglama type not previously labeled · ')+'Detector: '+guess+' · '+row.duration.toFixed(2)+' s · A4 '+row.reference+' Hz';
   info.append(title,detail);
   if(details.strings?.length){const list=document.createElement('ul');for(const string of details.strings){const item=document.createElement('li');item.textContent='String '+string.position+': '+(string.note==null?'Unknown note':names[string.note])+(string.octave==null?'':' · octave '+string.octave)+(string.cents==null?' · cents unknown':' · '+(string.cents>=0?'+':'')+string.cents+'¢');list.append(item);}info.append(list);}
   if(row.notes){const note=document.createElement('p');note.textContent=row.notes;info.append(note);}article.append(info);
   const actions=document.createElement('div');actions.className='row-actions';
   for(const [action,label] of [['play','Play strum'],['load','Review / edit label'],[row.deleted_at?'restore':'trash',row.deleted_at?'Restore':'Move to Trash']]){
    if(action==='load'&&row.deleted_at)continue;const button=document.createElement('button');button.textContent=label;button.dataset.caseAction=action;button.dataset.id=row.id;actions.append(button);
   }
   article.append(actions);$('strumCaseList').append(article);
  }
 }
 async action(button){
  const id=button.dataset.id,action=button.dataset.caseAction;button.disabled=true;if(action!=='play')this.lock(true);
  try{
   if(action==='play')await this.audio.playURL('/api/final-tone-tests/'+id+'/audio','Saved evaluation strum');
   else if(action==='load'){
    const row=this.rows.find(r=>r.id===id);const original=await this.api('/api/final-tone-tests/'+id+'/pcm');const bytes=Uint8Array.from(atob(original.audio),c=>c.charCodeAt(0));
    this.candidate({samples:new Float32Array(bytes.buffer),rate:row.rate,reference:row.reference,source:row.source,savedId:row.id});
    this.$('strumKnownTone').value=String(row.expected);this.stringFields.reset(row.instrumentDetails||{});this.$('strumCaseNotes').value=row.notes;this.$('strumCaseForm').scrollIntoView({block:'center'});this.notify('Editing the saved test case label. Its original detector result is preserved.');
   }else{this.audio.stop();await this.api('/api/final-tone-tests/'+id+'/'+action,{});if(this.current?.savedId===id)this.candidate(null);await this.refresh();this.notify(action==='trash'?'Test case moved to recoverable Trash.':'Test case restored.');}
  }finally{button.disabled=false;if(action!=='play')this.lock(false);}
 }
}
