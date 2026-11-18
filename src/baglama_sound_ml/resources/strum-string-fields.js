export const noteNames=['Do / C','Do♯ / C#','Re / D','Re♯ / D#','Mi / E','Fa / F','Fa♯ / F#','Sol / G','Sol♯ / G#','La / A','La♯ / A#','Si / B'];
export class StrumStringFields {
 constructor(catalog){
  this.catalog=catalog;this.rows=[];this.$=id=>document.getElementById(id);
  for(const instrument of catalog.instruments)this.$('strumBaglamaType').add(new Option(instrument.title,instrument.id));
  this.$('strumBaglamaType').onchange=()=>this.setTunings();
  this.$('strumArrangement').onchange=()=>this.render();
  this.$('strumKnownTone').onchange=()=>this.render(true);
 }
 instrument(){return this.catalog.instruments.find(i=>i.id===this.$('strumBaglamaType').value);}
 tuning(){return this.instrument()?.tunings.find(t=>t.id===this.$('strumArrangement').value);}
 setTunings(selected){
  const select=this.$('strumArrangement');select.replaceChildren(new Option('Choose arrangement…',''));
  for(const tuning of this.instrument()?.tunings||[])select.add(new Option(tuning.title,tuning.id));
  if(selected)select.value=selected;this.render();
 }
 reset(details={}){this.$('strumBaglamaType').value=details.instrumentID||'';this.setTunings(details.tuningID);this.render(false,details.strings||[]);}
 render(preserve=false,known=[]){
  const old=preserve?this.values():known;this.rows=[];const container=this.$('strumStringRows');container.replaceChildren();
  const tuning=this.tuning();if(!tuning){container.textContent='Choose baglama type and arrangement to show string rows.';return;}
  const selected=this.$('strumKnownTone').value;const variant=tuning.variants.find(v=>String(v.kararPitchClass)===selected)||tuning.variants[0];
  for(const course of variant.courses)for(const target of course.strings){
   const index=this.rows.length+1,previous=old.find(s=>s.stringID===target.id)||{};
   const row=document.createElement('div');row.className='string-observation';
   const heading=document.createElement('h4');heading.textContent='String '+index+' · '+({ust:'Upper / Üst',orta:'Middle / Orta',alt:'Lower / Alt'}[course.id]||'Course '+course.id);row.append(heading);
   const fields=document.createElement('div');fields.className='fields';
   const note=document.createElement('select');note.add(new Option('Unknown note',''));noteNames.forEach((n,i)=>note.add(new Option(n,String(i))));note.value=previous.note==null?'':String(previous.note);
   const octave=document.createElement('select');octave.add(new Option('Unknown octave',''));for(let i=0;i<=7;i++)octave.add(new Option(String(i),String(i)));octave.value=previous.octave==null?'':String(previous.octave);
   const cents=document.createElement('input');cents.type='text';cents.inputMode='decimal';cents.min='-1200';cents.max='1200';cents.step='any';cents.placeholder='Unknown (e.g. -12 or +4)';cents.value=previous.cents==null?'':String(previous.cents);
   for(const [name,control] of [['Note',note],['Octave (if known)',octave],['Cents + / − (if known)',cents]]){const label=document.createElement('label');label.append(document.createTextNode('String '+index+' · '+name),control);fields.append(label);}
   row.append(fields);container.append(row);this.rows.push({stringID:target.id,note,octave,cents});
  }
 }
 values(){return this.rows.map(row=>({stringID:row.stringID,note:row.note.value===''?null:Number(row.note.value),octave:row.octave.value===''?null:Number(row.octave.value),cents:row.cents.value.trim()===''?null:Number(row.cents.value.trim().replace(',','.'))}));}
 payload(){
  const instrumentID=this.$('strumBaglamaType').value,tuningID=this.$('strumArrangement').value;
  if(!instrumentID||!tuningID)throw Error('Choose baglama type and arrangement first.');
  const strings=this.values();for(const row of strings){if(row.cents!==null&&(!Number.isFinite(row.cents)||row.cents < -1200||row.cents>1200))throw Error('Cents must be between -1200 and +1200, or blank.');if(row.note===null&&(row.octave!==null||row.cents!==null))throw Error('Choose the string note before entering its octave or cents.');}
  return {instrumentID,tuningID,strings};
 }
}
