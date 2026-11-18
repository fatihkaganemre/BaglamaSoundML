const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const root=path.join(__dirname,'../src/baglama_sound_ml/resources');const url=s=>'data:text/javascript;base64,'+Buffer.from(s).toString('base64');const audio=url(fs.readFileSync(path.join(root,'lab-audio.js'),'utf8'));const fields=url(fs.readFileSync(path.join(root,'strum-string-fields.js'),'utf8'));const catalog=JSON.parse(fs.readFileSync(path.join(root,'capture-catalog.json'),'utf8'));const source=fs.readFileSync(path.join(root,'final-tone-examples.js'),'utf8').replace("'/lab-audio.js'",JSON.stringify(audio)).replace("'/strum-string-fields.js'",JSON.stringify(fields));
function environment(){const elements=new Map();global.Option=class{constructor(text,value){this.text=text;this.value=value;}};const node=()=>({value:'',textContent:'',checked:false,hidden:false,children:[],add(v){this.children.push(v);},append(...v){this.children.push(...v);},replaceChildren(){this.children=[];},addEventListener(){},scrollIntoView(){}});global.document={getElementById(id){if(!elements.has(id))elements.set(id,node());return elements.get(id);},createElement:node,createTextNode:text=>({textContent:text})};return id=>document.getElementById(id);}
test('labels require explicit real-audio consent and save the analyzed reference and exact PCM',async()=>{
 const $=environment();const {FinalToneExamples}=await import(url(source));let posted,notice;
 const examples=new FinalToneExamples({catalog,api:async(route,body)=>{if(body){posted=body;return {id:'saved',duplicate:false};}return {cases:[]};},audio:{},notify:message=>notice=message,lock(){}});
 const samples=new Float32Array([.1,.2,.3]);examples.candidate({samples,rate:48000,reference:442,source:'microphone'});
 assert.equal($('strumKnownTone').value,'');await examples.save();assert.equal(posted,undefined);
 $('strumCaseConsent').checked=true;await examples.save();assert.equal(posted,undefined);
 $('strumKnownTone').value='9';$('strumBaglamaType').value='kisaSap';examples.stringFields.setTunings('baglama');examples.stringFields.rows[0].note.value='9';examples.stringFields.rows[0].octave.value='2';examples.stringFields.rows[0].cents.value='-12.5';await examples.save();
 assert.equal(posted.expectedPitchClass,9);assert.equal(posted.referenceHertz,442);assert.equal(posted.instrumentID,'kisaSap');assert.equal(posted.strings.length,7);assert.equal(posted.strings[0].cents,-12.5);assert.equal(posted.strings[1].cents,null);assert.deepEqual(Buffer.from(posted.audio,'base64'),Buffer.from(samples.buffer));
 examples.candidate(null);posted=undefined;await examples.save();assert.equal(posted,undefined);assert.equal($('strumCaseForm').hidden,true);
});
test('a failed save keeps the labeled audio available for retry',async()=>{
 const $=environment();const {FinalToneExamples}=await import(url(source));let message;
 const examples=new FinalToneExamples({catalog,api:async(_,body)=>{if(body)throw Error('disk full');return {cases:[]};},audio:{},notify:text=>message=text,lock(){}});
 const candidate={samples:new Float32Array([.1]),rate:48000,reference:440,source:'WAV'};examples.candidate(candidate);$('strumCaseConsent').checked=true;$('strumKnownTone').value='7';$('strumBaglamaType').value='kisaSap';examples.stringFields.setTunings('baglama');await examples.save();assert.equal(examples.current,candidate);assert.match(message,/retry/);
});

test('changing setup changes ordered string rows and known final tone never fills measurements',async()=>{
 const $=environment();const {FinalToneExamples}=await import(url(source));
 const examples=new FinalToneExamples({catalog,api:async()=>({cases:[]}),audio:{},notify(){},lock(){}});
 examples.candidate({});$('strumBaglamaType').value='kisaSap';examples.stringFields.setTunings('baglama');assert.equal(examples.stringFields.rows.length,7);
 assert.equal(examples.stringFields.rows[0].cents.type,'text');let values=examples.stringFields.values();assert.ok(values.every(row=>row.note===null&&row.octave===null&&row.cents===null));
 examples.stringFields.rows[0].note.value='9';examples.stringFields.rows[0].cents.value='0';$('strumKnownTone').value='10';examples.stringFields.render(true);values=examples.stringFields.values();assert.equal(values[0].note,9);assert.equal(values[0].cents,0);examples.stringFields.rows[0].cents.value='+4.5';assert.equal(examples.stringFields.values()[0].cents,4.5);examples.stringFields.rows[0].cents.value='-12,5';assert.equal(examples.stringFields.values()[0].cents,-12.5);
 $('strumBaglamaType').value='cura';examples.stringFields.setTunings('baglama');assert.equal(examples.stringFields.rows.length,3);assert.ok(examples.stringFields.values().every(row=>row.note===null));
});
