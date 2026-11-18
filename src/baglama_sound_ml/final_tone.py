"""Experimental, model-free open-strum final-tone estimation. No capture/storage I/O."""
from __future__ import annotations
import math
import numpy as np
from .capture_catalog import catalog

def representative(matches):
    ordered=sorted(matches,key=lambda o:o['hz'])
    cumulative=np.cumsum([o['weight'] for o in ordered])
    return float(ordered[int(np.searchsorted(cumulative,cumulative[-1]/2))]['hz'])


NAMES=('Do / C','Do♯ / C#','Re / D','Re♯ / D#','Mi / E','Fa / F','Fa♯ / F#','Sol / G','Sol♯ / G#','La / A','La♯ / A#','Si / B')


def synthetic_strum(reference=440.):
    rate=48000;t=np.arange(rate*2)/rate;audio=np.zeros(len(t))
    for onset,midi in [(0.1,45),(.18,55),(.26,50)]:
        age=t-onset;envelope=np.where(age>=0,np.minimum(np.maximum(age,0)*150,1)*np.exp(-3*np.maximum(age,0)),0)
        hz=reference*2**((midi-69)/12)
        for h in range(1,7):audio+=envelope*np.sin(2*np.pi*hz*h*t)/h**1.4
    return (audio/max(np.max(np.abs(audio)),1)*.7).astype('<f4'),rate


def detect_final_tone(audio,rate,reference=440.):
    x=np.asarray(audio,dtype=np.float64)
    if type(rate) is not int or not 8000<=rate<=192000 or x.ndim!=1 or not rate*.4<=len(x)<=rate*8:
        raise ValueError('Use 0.4–8 seconds of mono audio at 8–192 kHz.')
    if not math.isfinite(reference) or not 400<=reference<=480 or not np.all(np.isfinite(x)) or np.max(np.abs(x))>1.01:
        raise ValueError('Audio must be finite PCM, with A4 between 400 and 480 Hz.')
    x=x-x.mean();rms=float(np.sqrt(np.mean(x*x)))
    result=dict(status='insufficient',finalTone=None,confidence=0.,tuningStatus='unknown',tuningToleranceCents=5.,confidenceMeaning='Heuristic evidence score, not a calibrated probability.',courses=[],candidates=[],observedPitches=[],message='Play all open courses in one clear strum and try again.',experimental=True,instrument='kisaSap',tuning='baglama',referenceHertz=reference)
    if rms<.001:return result
    # Normalize only this analysis copy; preserve input. 24 kHz keeps the FFT bounded.
    x=x/max(float(np.max(np.abs(x))),1e-8)
    target_rate=24000
    x=np.interp(np.arange(round(len(x)*target_rate/rate))*rate/target_rate,np.arange(len(x)),x)
    size=8192;hop=2048;window=np.hanning(size);observations=[]
    for start in range(0,max(1,len(x)-size+1),hop):
        frame=x[start:start+size]
        if len(frame)<size:continue
        if np.sqrt(np.mean(frame*frame))<.012:continue
        spectrum=np.abs(np.fft.rfft(frame*window));peak=float(spectrum.max())
        indices=np.flatnonzero((spectrum[1:-1]>spectrum[:-2])&(spectrum[1:-1]>=spectrum[2:]))+1
        indices=[i for i in indices if 65<=i*target_rate/size<=1200 and spectrum[i]>=peak*.075]
        fundamentals=[]
        for i in sorted(indices):
            values=np.log(np.maximum(spectrum[i-1:i+2],1e-12));den=values[0]-2*values[1]+values[2]
            correction=float(np.clip(.5*(values[0]-values[2])/den,-.5,.5)) if abs(den)>1e-12 else 0
            hz=(i+correction)*target_rate/size
            # Reject resolved overtones; octave partners contribute the same pitch class.
            if any(2<=round(hz/f)<=12 and abs(1200*math.log2(hz/(f*round(hz/f))))<22 for f,_ in fundamentals):continue
            midi=69+12*math.log2(hz/reference);nearest=round(midi);cents=(midi-nearest)*100
            if abs(cents)<=30:
                fundamentals.append((hz,float(spectrum[i]/peak)))
                observations.append(dict(hz=hz,pitchClass=nearest%12,weight=float(spectrum[i]/peak),cents=cents,frame=start//hop))
    evidence=np.zeros(12);counts=np.zeros(12,dtype=int)
    for pc in range(12):
        matches=[o for o in observations if o['pitchClass']==pc]
        frames={o['frame'] for o in matches};counts[pc]=len(frames)
        evidence[pc]=sum(max(o['weight'] for o in matches if o['frame']==f) for f in frames)
        if matches:
            result['observedPitches'].append(dict(note=NAMES[pc],frequencyHertz=representative(matches),frames=len(frames)))
    if evidence.sum()==0:return result
    evidence/=evidence.sum()
    instrument=next(i for i in catalog()['instruments'] if i['id']=='kisaSap')
    tuning=next(t for t in instrument['tunings'] if t['id']=='baglama')
    ranked=[]
    for variant in tuning['variants']:
        courses=[dict(course=c['id'],pitchClass=c['strings'][0]['note']) for c in variant['courses']]
        pcs=[c['pitchClass'] for c in courses]
        coverage=float(evidence[pcs].sum());weakest=float(min(evidence[pcs]))
        score=coverage*.65+min(1.,weakest/.15)*.35
        ranked.append(dict(variantID=variant['id'],pitchClass=variant['kararPitchClass'],name=NAMES[variant['kararPitchClass']],score=score,coverage=coverage,courses=courses))
    ranked.sort(key=lambda r:r['score'],reverse=True)
    best=ranked[0];margin=best['score']-ranked[1]['score']
    result['candidates']=[dict(name=r['name'],score=round(r['score'],3)) for r in ranked[:3]]
    pcs=[c['pitchClass'] for c in best['courses']]
    if best['coverage']>=.8 and min(evidence[pcs])>=.08 and min(counts[pcs])>=3 and margin>=.12:
        result.update(status='detected',finalTone=dict(name=best['name'],pitchClass=best['pitchClass'],variantID=best['variantID']),confidence=round(min(best['score'],margin/.3),3),message='Likely final tone from the open-course pattern. Confirm by listening; this prototype is not validated on real full strums yet.')
        for c in best['courses']:
            matches=[o for o in observations if o['pitchClass']==c['pitchClass']]
            hz=representative(matches)
            midi=69+12*math.log2(hz/reference)
            ordered=sorted(matches,key=lambda o:abs(o['cents']))
            cumulative=np.cumsum([o['weight'] for o in ordered])
            error90=abs(ordered[int(np.searchsorted(cumulative,cumulative[-1]*.9))]['cents'])
            result['courses'].append(dict(course=c['course'],note=NAMES[c['pitchClass']],frequencyHertz=hz,centsFromNote=round((midi-round(midi))*100,2),inTune=error90<=5,evidence=round(float(evidence[c['pitchClass']]),3)))
        result['tuningStatus']='inTune' if all(c['inTune'] for c in result['courses']) else 'needsTuning'
        result['message']=('Detected course pitches are within ±5 cents. This does not verify every physical string.' if result['tuningStatus']=='inTune' else 'The course pattern suggests this final tone, but one or more detected courses need tuning.')+' Experimental: confirm with a tuner.'
    return result
