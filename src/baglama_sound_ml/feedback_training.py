"""Subjective feedback focuses supervised fitting; only real audio supplies targets."""
from __future__ import annotations
import html
import json
import math
from pathlib import Path
import numpy as np
from .audio import write_wav
from .synthesis import neural


def distance(a, b):
    return abs(1200 * math.log2(a / b))


def plan_feedback(report: dict, training: list, validation: list) -> dict:
    """At most 2x real-frame loss, within 100 cents/same course; never tune on heldout pitches."""
    focuses, ignored = [], []
    def add(render, source, overall=0., attack=0., decay=0.):
        if render.get('deleted_at') or render.get('method') != 'neural':
            ignored.append(dict(source=source, reason='inactive or non-neural clip')); return
        p = render['parameters']; hz = p.get('frequencyHertz',0); course = p.get('course')
        if not isinstance(hz,(int,float)) or not math.isfinite(hz) or hz <= 0:
            ignored.append(dict(source=source, reason='invalid pitch')); return
        if any(r['course']==course and distance(hz,r['frequency_hz'])<=35 for r in validation):
            ignored.append(dict(source=source, reason='held-out pitch; listening comparison only')); return
        matches=[r['identity'] for r in training if r['course']==course and distance(hz,r['frequency_hz'])<=100]
        if not matches or max(overall,attack,decay)<=0:
            ignored.append(dict(source=source, reason='no local real training target or no reported weakness')); return
        focuses.append(dict(source=source,renderId=render['id'],modelId=render['model_id'],frequencyHertz=hz,course=course,
                            overall=overall,attack=attack,decay=decay,realTrainingIdentities=matches))
    for rating in report.get('ratings',[]):
        tags=set(rating['tags'])
        overall=max((3-rating['naturalness'])/2, float(bool(tags & {'synthetic','noisy'})),0.)
        attack=max((3-rating['attack'])/2,float('weak-attack' in tags),0.)
        decay=max((3-rating['decay'])/2,float(bool(tags & {'short-decay','long-decay'})),0.)
        add(rating['render'],'rating:'+rating['render_id'],overall,attack,decay)
    # A preference tells us where a neural clip lost, not how to copy the winner.
    for comparison in report.get('comparisons',[]):
        preference=comparison['preference']
        losers=['a','b'] if preference=='neither' else ['b'] if preference=='a' else ['a'] if preference=='b' else []
        for side in losers:
            render=report.get('comparisonRenders',{}).get(comparison[side+'_id'])
            if render:
                add(render,'comparison:'+comparison['id']+':'+side,overall=.5)
    return dict(method='bounded-real-target-loss-weighting-v1',focuses=focuses,ignored=ignored,
                ratings=len(report.get('ratings',[])),comparisons=len(report.get('comparisons',[])),
                maxWeight=2.,radiusCents=100,heldoutExclusionCents=35,
                caveat='Heuristic training emphasis, not a learned reward model. Positive clips are listening regressions only; generated PCM never supplies training targets. Pitch opinions do not change frequency labels.')


def frame_weights(row: dict, times: np.ndarray, plan: dict) -> np.ndarray:
    emphasis=np.zeros(len(times),dtype=np.float32)
    for focus in plan.get('focuses',[]):
        if row['identity'] not in focus['realTrainingIdentities']:
            continue
        proximity=max(0.,1-distance(row['frequency_hz'],focus['frequencyHertz'])/100)
        amount=np.maximum(focus['overall'],np.where(times < .12,focus['attack'],focus['decay']))
        # Repeated ratings/pairs do not accumulate unlimited influence.
        emphasis=np.maximum(emphasis,proximity*amount)
    return 1+np.minimum(emphasis,1)


def feedback_comparison(report, store, model: Path, output: Path, plan: dict):
    """Replay exact rated/generated audio against the new renderer with identical controls."""
    candidates={r['render_id']:r['render'] for r in report['ratings']}
    candidates.update(report.get('comparisonRenders',{}))
    candidates={k:v for k,v in candidates.items() if not v.get('deleted_at') and v['method']=='neural'}
    cards=[]; cases=[]
    for index, (identity,render) in enumerate(sorted(candidates.items())[:50]):
        p=render['parameters']
        generated,_=neural(model,p['frequencyHertz'],p['course'],p['duration'],p.get('seed',7))
        before=f'feedback-{index:02d}-before.wav';after=f'feedback-{index:02d}-after.wav'
        write_wav(output/before,store.audio(identity));write_wav(output/after,generated)
        cases.append(dict(renderId=identity,previousModel=render['model_id'],parameters=p,before=before,after=after))
        cards.append(f'<section><h2>{html.escape(p["course"])} · {p["frequencyHertz"]:.2f} Hz</h2><p>Previously rated clip</p><audio controls src="{before}"></audio><p>New model, same controls</p><audio controls src="{after}"></audio></section>')
    (output/'feedback-comparison.json').write_text(json.dumps(dict(cases=cases,totalEligible=len(candidates),displayLimit=50,plan=plan),indent=2)+'\n')
    (output/'feedback.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Feedback regression listening</title><style>body{font:18px system-ui;max-width:900px;margin:40px auto;padding:20px}section{border:1px solid #888;padding:16px;margin:20px 0}audio{max-width:100%}</style><h1>Feedback regression listening</h1><p>Subjective comparison, not an independent test. Training uses only real targets. Labels are visible; use app blind A/B for a less biased preference.</p>'+(''.join(cards) or '<p>No active rated neural clips or neural A/B clips yet. Add feedback in the app, then run make train again.</p>')+'</html>')
    index=output/'index.html';text=index.read_text();index.write_text(text.replace('<h1>','<p><a href="feedback.html">Listen to feedback clips with the new model</a></p><h1>',1))
    return dict(listeningCases=len(cases),totalEligible=len(candidates),appliedFocuses=len(plan['focuses']),ignored=len(plan['ignored']))
