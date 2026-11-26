import {initFinalTone} from '/final-tone-ui.js';
import {LabAudio,base64} from '/lab-audio.js';
import {SampleEditor} from '/capture-ui.js';
const $=id=>document.getElementById(id),en=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'],tr=['Do','Do♯','Re','Re♯','Mi','Fa','Fa♯','Sol','Sol♯','La','La♯','Si'];
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={config:null,samples:[],renders:[],feedback:null,current:null,comparison:null,heard:new Set(),openSampleGroups:new Set(),sampleGroupLimits:new Map(),collapseSearchGroups:false,view:'library',tool:'generate'};
let editor,finalTone;
function notify(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);}
const audio=new LabAudio(message=>$('playbackStatus').textContent=message);
async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-Baglama-Token':state.config.token},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});let result;try{result=await response.json();}catch{throw Error('The local server did not return valid data. Check the Terminal window.');}if(!response.ok)throw Error(result.error||'Local request failed.');return result;}
async function guarded(action){try{await action();}catch(error){notify(error.message,true);}}
function options(select,values,placeholder){const previous=select.value;select.replaceChildren();if(placeholder!==undefined)select.add(new Option(placeholder,''));for(const value of values)select.add(new Option(value.title,value.id));if([...select.options].some(o=>o.value===previous))select.value=previous;}
function noteLabel(target){return tr[target.note]+' / '+en[target.note]+(target.octave!==undefined?target.octave:' · octave unspecified');}
function leavePlaygroundTool(){
 if(state.tool==='finaltone')finalTone?.leave();
 if(state.tool==='continuation'){
  $('continuationReport').contentDocument?.querySelectorAll('audio').forEach(player=>player.pause());
 }
}
function selectPlaygroundTool(name){
 if(state.tool!==name){
  leavePlaygroundTool();
  audio.stop();
 }
 state.tool=name;
 document.querySelectorAll('.playground-tool').forEach(panel=>panel.hidden=panel.id!=='tool-'+name);
 document.querySelectorAll('button[data-tool]').forEach(button=>{
  button.setAttribute('aria-pressed',String(button.dataset.tool===name));
 });
}
async function runContinuation(){
 const button=$('runContinuation'),status=$('continuationStatus');
 button.disabled=true;
 status.textContent='Generating continuations from the recorded first halves…';
 try{
  const result=await api('/api/continuations',{});
  const report=$('continuationReport'),link=$('openContinuation');
  report.src=result.report;
  link.href=result.report;
  report.hidden=link.hidden=false;
  status.textContent=`${result.recordings} completed · ${result.skipped} skipped`;
 }catch(error){
  status.textContent=error.message;
 }finally{
  button.disabled=false;
 }
}
async function view(name){if(state.view==='playground'&&name!=='playground')leavePlaygroundTool();if(editor)editor.close();audio.stop();state.view=name;document.querySelectorAll('.view').forEach(panel=>panel.hidden=panel.id!=='view-'+name);document.querySelectorAll('nav button[data-view]').forEach(b=>{if(b.dataset.view===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});if(name==='library')await refreshSamples();if(name==='feedback')await refreshFeedback();}
async function refreshSamples(){const data=await api('/api/samples?trash='+$('filterTrash').value);state.samples=data.samples;$('sampleCount').textContent=data.samples.length;const values=[...new Set(data.samples.map(r=>r.label.variantID||'unspecified'))].sort();options($('filterVariant'),values.map(v=>({id:v,title:v.replace('karar-','')})),'All final tones');renderLibrary();}
function setupTitle(label){const inst=state.config.catalog.instruments.find(i=>i.id===label.instrumentID);const tuning=inst?.tunings.find(t=>t.id===label.tuningID);const v=tuning?.variants.find(v=>v.id===label.variantID);return (inst?.title||label.instrumentID)+' / '+(tuning?.title||label.tuningID)+' · '+(v?tr[v.kararPitchClass]+' / '+en[v.kararPitchClass]:label.variantID);}
function sampleTitle(row){return (row.label.physicalStringNumber?'String '+row.label.physicalStringNumber:'String '+row.label.stringID)+' · '+noteLabel(row.label.target);}
function sampleGroups(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = JSON.stringify([row.label.instrumentID, row.label.tuningID, row.label.variantID]);
    if (!groups.has(key)) groups.set(key, {key, label: row.label, rows: [], strings: new Map()});
    const group = groups.get(key);
    const stringKey = JSON.stringify([key, row.label.stringID]);
    if (!group.strings.has(stringKey)) group.strings.set(stringKey, {key: stringKey, rows: []});
    group.rows.push(row);
    group.strings.get(stringKey).rows.push(row);
  }
  return [...groups.values()];
}
function sampleRow(row) { const measured=row.analysis.estimatedFrequencyHertz,estimate=Number.isFinite(measured)?measured.toFixed(2)+' Hz':'No reliable pitch';const warning=(row.analysis.warnings||[]).join(' ');const usage=row.modelUsage==='training'?'Used to train current model':row.modelUsage==='validation'?'Used for current checkpoint validation':'Not used by current model';return `<article class="list-row"><div><h3>${esc(sampleTitle(row))}</h3><span class="badge ${row.analysis.quality==='consistent'?'consistent':'uncertain'}">${esc(row.analysis.quality||'Not analyzed')}</span> <span class="subtle">${esc(estimate)} · ${row.duration.toFixed(2)} s · ${(row.rate/1000).toFixed(1)} kHz</span><div class="row-meta">${esc(setupTitle(row.label))} · ${esc(row.source)}</div><div class="row-meta">Session: ${esc(row.session||'Unassigned')} · ${esc(usage)}</div>${row.label.measuredGroundTruthHertz?'<div class="row-meta">Independent ground truth: '+esc(row.label.measuredGroundTruthHertz)+' Hz · '+esc(row.label.measuredGroundTruthSource)+'</div>':''}${warning?'<div class="row-meta">'+esc(warning)+'</div>':''}</div><div class="row-actions"><button data-action="sample-play" data-id="${row.id}" aria-label="Play ${esc(sampleTitle(row))}">Play</button>${row.deleted_at?'':'<button data-action="sample-edit" data-id="'+row.id+'">Waveform / trim</button>'}<button data-action="sample-${row.deleted_at?'restore':'trash'}" data-id="${row.id}" class="${row.deleted_at?'':'danger'}">${row.deleted_at?'Restore':'Move to Trash'}</button></div></article>`; }
function renderLibrary() {
  const query = $('search').value.toLowerCase().trim();
  const selected = $('filterVariant').value, quality = $('filterQuality').value;
  const rows = state.samples.filter(row =>
    (!selected || row.label.variantID === selected) && (!quality || row.analysis.quality === quality) &&
    (!query || [sampleTitle(row), setupTitle(row.label), row.session, row.detail,
      row.label.instrumentID, row.label.tuningID, row.analysis.estimatedFrequencyHertz].join(' ').toLowerCase().includes(query)));
  const groups = sampleGroups(rows);
  const searching = !!query && !state.collapseSearchGroups;
  const isOpen = key => searching || state.openSampleGroups.has(key);
  const disclosure = (key, title, count, contents, nested = false) => {
    const open = isOpen(key);
    return `<details class="${nested ? 'string-group' : 'sample-group'}" data-sample-group="${esc(key)}" data-rendered-open="${open ? '1' : '0'}" data-total-count="${count}"${open ? ' open' : ''}>
      <summary><span>${esc(title)}</span><span class="badge">${count} ${count === 1 ? 'sample' : 'samples'}</span></summary>
      <div class="${nested ? 'group-takes' : 'string-groups'}">${nested ? `<div class="take-list">${contents}</div>` : contents}</div></details>`;
  };
  $('librarySummary').textContent = `${rows.length} matching samples · ${groups.length} final-tone groups. Open a group, then a physical string, to see its takes.`;
  $('reviewHome').append($('review'));
  $('sampleList').innerHTML = groups.map(group => {
    const strings = [...group.strings.values()].sort((a, b) =>
      (a.rows[0].label.physicalStringNumber ?? Infinity) - (b.rows[0].label.physicalStringNumber ?? Infinity));
    const contents = strings.map(string => {
      const limit = state.sampleGroupLimits.get(string.key) || 10;
      const takes = string.rows.slice(0, limit).map(sampleRow).join('');
      const more = string.rows.length > limit ? `<button data-more-takes="${esc(string.key)}">Show more takes (${string.rows.length - limit} remaining)</button>` : '';
      return disclosure(string.key, sampleTitle(string.rows[0]), string.rows.length, takes + more, true);
    }).join('');
    return disclosure(group.key, setupTitle(group.label), group.rows.length, contents);
  }).join('') || '<div class="card">No samples match this view. Import a Baglamator ZIP.</div>';
  if(editor?.sampleId){
    const button=$('sampleList').querySelector(`button[data-action="sample-edit"][data-id="${CSS.escape(editor.sampleId)}"]`);
    const takes=button?.closest('.group-takes');
    if(takes?.closest('.string-group').open && takes.closest('.sample-group').open) takes.append($('review'));
    else editor.close();
  }
  $('expandSamples').disabled = groups.length === 0;
  $('collapseSamples').disabled = groups.length === 0;
}

function generationRequest(method=$('genMethod').value){const note=Number($('genNote').value),octave=Number($('genOctave').value),reference=Number($('genReference').value),cents=Number($('genCents').value),duration=Number($('genDuration').value),seed=Number($('genSeed').value);const hz=reference*2**((((octave+1)*12+note-69)+cents/100)/12);if(!Number.isFinite(hz)||hz<40||hz>2000||duration<.1||duration>3||!Number.isFinite(duration)||!Number.isInteger(seed)||seed<0||seed>4294967295||reference<400||reference>480||!Number.isFinite(cents)||Math.abs(cents)>1200)throw Error('Choose valid pitch, duration, reference, cents and seed settings.');return {frequencyHertz:hz,course:$('genCourse').value,method,duration,seed,referenceHertz:reference,cents,note:en[note]+octave};}
function renderTitle(row){const p=row.parameters;return (row.method==='neural'?'ML':'Sample')+' · '+(p.note||p.frequencyHertz.toFixed(2)+' Hz')+' · '+p.course+' · '+p.duration+' s'+(row.method==='neural'?' · seed '+p.seed:'');}
function showCandidate(row,rating){state.current=row;$('downloadRender').hidden=false;$('downloadRender').href='/api/renders/'+row.id+'/audio';$('downloadRender').download='BaglamaSoundML-'+row.id+'.wav';$('renderDescription').textContent=renderTitle(row)+' · '+row.parameters.frequencyHertz.toFixed(2)+' Hz';$('replayRender').disabled=false;$('ratingForm').hidden=false;$('ratingForm').reset();$('favorite').checked=!!row.favorite;if(rating){for(const key of ['naturalness','attack','decay'])$(key).value=rating[key];$('pitchImpression').value=rating.pitch_impression;$('ratingNote').value=rating.note;document.querySelectorAll('#feedbackTags input').forEach(input=>input.checked=rating.tags.includes(input.value));}}
async function refreshFeedback(){const [renders,feedback]=await Promise.all([api('/api/renders'),api('/api/feedback')]);state.renders=renders.renders;state.feedback=feedback;$('feedbackCount').textContent=feedback.summary.ratedSounds;const labels=state.renders.map(r=>({id:r.id,title:renderTitle(r)+' · '+r.model_id.slice(0,8)+' · '+r.id.slice(0,6)}));options($('compareFirst'),labels,'Choose a candidate');options($('compareSecond'),labels,'Choose a different candidate');const s=feedback.summary,issues=Object.entries(s.issueCounts).filter(([,n])=>n).map(([tag,n])=>tag+': '+n).join(' · ')||'No issue tags yet';$('feedbackSummary').innerHTML=`<div class="stat"><strong>${s.ratedSounds}</strong><span>distinct sounds rated</span></div><div class="stat"><strong>${s.completedComparisons}</strong><span>A/B preferences saved</span></div><div class="stat"><strong>${s.preferenceWins.neural||0} / ${s.preferenceWins.sample||0}</strong><span>ML / sample preference wins (subjective)</span></div><p class="subtle">${esc(issues)}</p>`;
const displayed=$('renderTrash').value==='1'?(await api('/api/renders?trash=1')).renders:state.renders;
$('renderList').innerHTML=displayed.map(row=>`<article class="list-row"><div><h3>${row.favorite?'★ Favorite · ':''}${esc(renderTitle(row))}</h3><div class="row-meta">Generated audio · ${esc(row.model_id.slice(0,12))} · ${esc(new Date(row.created_at).toLocaleString())}</div></div><div class="row-actions"><button data-action="render-play" data-id="${row.id}">Play</button><button data-action="${row.deleted_at?'render-restore':'render-rate'}" data-id="${row.id}">${row.deleted_at?'Restore':'Rate / revise'}</button>${row.deleted_at?'':'<button data-action="render-trash" data-id="'+row.id+'" class="danger">Move to Trash</button>'}</div></article>`).join('')||'<div class="card">Generate a sound to begin your listening notebook.</div>';
$('ratingHistory').innerHTML=feedback.ratings.map(r=>`<article class="list-row"><div><h3>${esc(renderTitle(r.render))} · naturalness ${r.naturalness}/5</h3><div class="row-meta">Attack ${r.attack}/5 · decay ${r.decay}/5 · pitch impression: ${esc(r.pitch_impression)}</div><div class="row-meta">${esc(r.tags.join(', '))}${r.note?' · '+esc(r.note):''}</div></div><span class="badge">Preference data, not ground truth</span></article>`).join('')||'<p class="subtle">No ratings saved yet.</p>';
$('comparisonHistory').innerHTML=feedback.comparisons.map(c=>{const winner=c.preference==='a'?c.methodA:c.preference==='b'?c.methodB:c.preference;return `<article class="list-row"><div><h3>${c.parameters.frequencyHertz.toFixed(2)} Hz · ${esc(c.parameters.course)} · preference: ${esc(winner)}</h3><div class="row-meta">${esc(c.note||'No note added')}</div></div><span class="badge">Same requested pitch</span></article>`;}).join('')||'<p class="subtle">No comparisons saved yet.</p>';}
async function makeComparison(first,second){state.comparison=await api('/api/comparisons',{first,second});state.heard.clear();$('comparison').hidden=false;$('comparisonResult').textContent='';$('preference').value='';$('comparisonNote').value='';$('savePreference').disabled=true;$('comparisonHeard').textContent='Listen to both clips before choosing.';$('comparisonDescription').textContent=state.comparison.frequencyHertz.toFixed(2)+' Hz · '+state.comparison.course+' · methods randomly assigned to A and B';}
async function generate(event){event.preventDefault();const buttons=$('generateForm').querySelectorAll('button');buttons.forEach(b=>b.disabled=true);try{audio.stop();await audio.enable();notify('Generating locally…');const row=await api('/api/renders',generationRequest());showCandidate(row);await audio.playURL('/api/renders/'+row.id+'/audio',renderTitle(row),$('renderWave'));await refreshFeedback();notify('Generated candidate saved locally. Listen, then rate it or keep it as a favorite.');}catch(error){notify(error.message,true);}finally{buttons.forEach(b=>b.disabled=false);}}
async function init(){
 state.config=await api('/api/config');finalTone=initFinalTone({api,audio,notify,catalog:state.config.catalog});editor=new SampleEditor({api,audio,notify,saved:refreshSamples});
 for(const id of ['naturalness','attack','decay'])options($(id),[1,2,3,4,5].map(n=>({id:String(n),title:n+' / 5'+(n===1?' · poor':n===5?' · convincing':'')})),'Choose a score');
 $('feedbackTags').innerHTML=[['synthetic','Too synthetic'],['weak-attack','Weak attack'],['short-decay','Decay too short'],['long-decay','Decay too long'],['noisy','Unwanted noise'],['wrong-pitch','Pitch sounds wrong']].map(([tag,title])=>`<label><input type="checkbox" value="${tag}">${title}</label>`).join('');
 options($('genNote'),en.map((name,i)=>({id:String(i),title:tr[i]+' / '+name})));$('genNote').value='8';
 document.querySelectorAll('nav button[data-view]').forEach(button=>button.onclick=()=>guarded(()=>view(button.dataset.view)));
 document.querySelectorAll('button[data-tool]').forEach(button=>button.onclick=()=>selectPlaygroundTool(button.dataset.tool));
 $('runContinuation').onclick=runContinuation;
 for (const id of ['search','filterVariant','filterQuality']) $(id).addEventListener('input', () => {
    state.collapseSearchGroups = false;
    renderLibrary();
  });
  $('filterTrash').onchange = () => guarded(refreshSamples);
  $('sampleList').addEventListener('toggle', event => {
    const group = event.target;
    if (!group.matches('details[data-sample-group]') || !group.isConnected) return;
    const open = group.open ? '1' : '0';
    if (group.dataset.renderedOpen === open) return;
    group.dataset.renderedOpen = open;
    if (group.open) state.openSampleGroups.add(group.dataset.sampleGroup);
    else {
      state.openSampleGroups.delete(group.dataset.sampleGroup);
      if(group.contains($('review')))editor.close();
    }
  }, true);
  $('sampleList').addEventListener('click', event => {
    const button = event.target.closest('button[data-more-takes]');
    if (!button) return;
    const key = button.dataset.moreTakes;
    state.sampleGroupLimits.set(key, (state.sampleGroupLimits.get(key) || 10) + 10);
    renderLibrary();
  });
  $('expandSamples').onclick = () => {
    for (const group of sampleGroups(state.samples)) {
      state.openSampleGroups.add(group.key);
      for (const string of group.strings.values()) state.openSampleGroups.add(string.key);
    }
    state.collapseSearchGroups = false;
    renderLibrary();
  };
  $('collapseSamples').onclick = () => {
    state.openSampleGroups.clear();
    state.collapseSearchGroups = true;
    renderLibrary();
  };
 $('importZip').onclick=()=>$('zipFile').click();$('zipFile').onchange=event=>guarded(async()=>{const file=event.target.files[0];event.target.value='';if(!file)return;if(file.size>40*1024*1024)throw Error('Import one ZIP smaller than 40 MB at a time.');$('importZip').disabled=true;try{notify('Importing original captures locally…');const result=await api('/api/import',{filename:file.name,archive:base64(new Uint8Array(await file.arrayBuffer()))});await refreshSamples();notify('Imported '+result.added+' recordings; '+result.duplicates+' duplicates skipped.');}finally{$('importZip').disabled=false;}});
 document.addEventListener('click',event=>{const button=event.target.closest('button[data-action]');if(!button)return;guarded(async()=>{const action=button.dataset.action,id=button.dataset.id;button.disabled=true;try{if(action==='sample-edit'){button.closest('.group-takes').append($('review'));await editor.open(state.samples.find(r=>r.id===id),sampleTitle(state.samples.find(r=>r.id===id)));}else if(action==='sample-play'){const row=state.samples.find(r=>r.id===id);await audio.playURL('/api/samples/'+id+'/audio',sampleTitle(row));}else if(action==='sample-trash'||action==='sample-restore'){editor.close();audio.stop();await api('/api/samples/'+id+'/'+(action==='sample-trash'?'trash':'restore'),{});await refreshSamples();notify(action==='sample-trash'?'Moved to Trash. Restore it using the View filter.':'Restored.');}else if(action==='render-play'){const row=state.renders.find(r=>r.id===id);await audio.playURL('/api/renders/'+id+'/audio',row?renderTitle(row):'Generated sound');}else if(action==='render-rate'){const row=state.renders.find(r=>r.id===id);await view('playground');selectPlaygroundTool('generate');showCandidate(row,state.feedback.ratings.find(r=>r.render_id===id));await audio.playURL('/api/renders/'+id+'/audio',renderTitle(row),$('renderWave'));}else if(action==='render-restore'){await api('/api/renders/'+id+'/restore',{});await refreshFeedback();notify('Generated candidate restored.');}else if(action==='render-trash'){audio.stop();await api('/api/renders/'+id+'/trash',{});await refreshFeedback();notify('Generated candidate hidden. Existing feedback remains saved.');}}finally{button.disabled=false;}});});
 $('generateForm').onsubmit=generate;$('replayRender').onclick=()=>guarded(()=>audio.playURL('/api/renders/'+state.current.id+'/audio',renderTitle(state.current),$('renderWave')));
 document.querySelectorAll('[data-preset]').forEach(button=>button.onclick=()=>{const[note,octave,course]=button.dataset.preset.split(',');$('genNote').value=note;$('genOctave').value=octave;$('genCourse').value=course;});
 $('ratingForm').onsubmit=event=>{event.preventDefault();guarded(async()=>{const button=$('ratingForm').querySelector('button[type=submit]');button.disabled=true;try{await api('/api/renders/'+state.current.id+'/feedback',{naturalness:Number($('naturalness').value),attack:Number($('attack').value),decay:Number($('decay').value),pitchImpression:$('pitchImpression').value,tags:[...document.querySelectorAll('#feedbackTags input:checked')].map(i=>i.value),note:$('ratingNote').value,favorite:$('favorite').checked});await refreshFeedback();notify('Feedback saved for this exact sound. The model and real-recording dataset have not changed.');}finally{button.disabled=false;}});};
 $('compareMethods').onclick=()=>guarded(async()=>{const buttons=$('generateForm').querySelectorAll('button');buttons.forEach(b=>b.disabled=true);try{audio.stop();notify('Generating a same-pitch ML/sample pair…');const first=await api('/api/renders',generationRequest('neural'));const second=await api('/api/renders',generationRequest('sample'));await view('feedback');await makeComparison(first.id,second.id);notify('Comparison ready. Listen to both sides, then choose your preference.');}finally{buttons.forEach(b=>b.disabled=false);}});
 $('startComparison').onclick=()=>guarded(()=>makeComparison($('compareFirst').value,$('compareSecond').value));
 for(const side of ['a','b'])$('play'+side.toUpperCase()).onclick=()=>guarded(async()=>{if(!state.comparison)return;const played=await audio.playURL(state.comparison[side==='a'?'audioA':'audioB'],'Blind clip '+side.toUpperCase());if(played){state.heard.add(side);$('comparisonHeard').textContent=state.heard.size===2?'Both clips played. Choose your preference.':'One clip played; listen to the other.';$('savePreference').disabled=state.heard.size!==2;}});
 $('renderTrash').onchange=()=>guarded(refreshFeedback);$('stopAB').onclick=()=>audio.stop();$('savePreference').onclick=()=>guarded(async()=>{if(state.heard.size!==2)throw Error('Listen to both clips first.');if(!$('preference').value)throw Error('Choose your preference.');const result=await api('/api/comparisons/'+state.comparison.id+'/feedback',{preference:$('preference').value,note:$('comparisonNote').value});$('comparisonResult').textContent='Saved. A was '+result.methodA+' ('+result.modelA.slice(0,8)+'); B was '+result.methodB+' ('+result.modelB.slice(0,8)+'). No automatic retraining.';await refreshFeedback();notify('A/B preference saved with the exact candidate pair and settings.');});
 await refreshSamples();await refreshFeedback();notify('Local library ready · '+state.samples.length+' real recordings. Microphone off.');
}
init().catch(error=>notify('Could not open the lab: '+error.message+' Start it using ./scripts/listen.sh.',true));
