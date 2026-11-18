"""Generated clips, subjective ratings and same-pitch blind A/B preferences."""
from __future__ import annotations
import hashlib
import json
import math
import secrets
import uuid
import numpy as np
from .local_library import LocalLibrary, now

TAGS = ('synthetic','weak-attack','short-decay','long-decay','noisy','wrong-pitch')


class FeedbackStore:
    def __init__(self, library: LocalLibrary):
        self.library=library

    def add_render(self, audio: np.ndarray, parameters: dict, model_id: str, method: str) -> dict:
        identity=uuid.uuid4().hex
        raw=audio.astype('<f4').tobytes()
        (self.library.root/'renders'/f'{identity}.f32').write_bytes(raw)
        with self.library.connect() as db:
            db.execute('INSERT INTO renders VALUES (?,?,?,?,?,0,?,NULL)',
                       (identity,hashlib.sha256(raw).hexdigest(),json.dumps(parameters),model_id,method,now()))
        return self.render(identity)

    def render(self, identity: str) -> dict:
        with self.library.connect() as db:
            row=db.execute('SELECT * FROM renders WHERE id=?',(identity,)).fetchone()
        if not row:
            raise KeyError('Generated sound not found.')
        item=dict(row)
        item['parameters']=json.loads(item['parameters'])
        item['kind']='generated'
        return item

    def audio(self, identity: str) -> np.ndarray:
        row=self.render(identity)
        return np.frombuffer((self.library.root/'renders'/f'{row["id"]}.f32').read_bytes(),dtype='<f4').astype(np.float64)

    def renders(self, trash: bool = False) -> list[dict]:
        with self.library.connect() as db:
            rows=db.execute('SELECT id FROM renders WHERE deleted_at IS '+('NOT NULL' if trash else 'NULL')+' ORDER BY created_at DESC').fetchall()
        return [self.render(row['id']) for row in rows]

    def rate(self, identity: str, value: dict) -> dict:
        render=self.render(identity)
        if render['deleted_at']:
            raise ValueError('Restore this generated sound before rating it.')
        scores=[]
        for key in ('naturalness','attack','decay'):
            score=value.get(key)
            if type(score) is not int or not 1 <= score <= 5:
                raise ValueError('Choose naturalness, attack and decay scores from 1 to 5.')
            scores.append(score)
        impression=value.get('pitchImpression')
        if impression not in ('okay','wrong','unsure'):
            raise ValueError('Choose a pitch impression; this is a listening opinion, not a frequency measurement.')
        tags=value.get('tags',[])
        if not isinstance(tags,list) or any(t not in TAGS for t in tags):
            raise ValueError('Unknown feedback tag.')
        note=str(value.get('note','')).strip()[:1000]
        with self.library.connect() as db:
            db.execute('''INSERT INTO ratings VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(render_id) DO UPDATE SET
                       naturalness=excluded.naturalness,attack=excluded.attack,decay=excluded.decay,
                       pitch_impression=excluded.pitch_impression,tags=excluded.tags,note=excluded.note,updated_at=excluded.updated_at''',
                       (identity,*scores,impression,json.dumps(sorted(set(tags))),note,now()))
            db.execute('UPDATE renders SET favorite=? WHERE id=?',(int(bool(value.get('favorite',False))),identity))
        return dict(saved=True,renderId=identity,trainingChanged=False)

    def comparison(self, first: str, second: str) -> dict:
        left,right=self.render(first),self.render(second)
        if left['deleted_at'] or right['deleted_at']:
            raise ValueError('Choose two active generated sounds.')
        if left['identity']==right['identity']:
            raise ValueError('These clips are identical. Generate a different method or seed first.')
        a,b=left['parameters'],right['parameters']
        if abs(1200*math.log2(a['frequencyHertz']/b['frequencyHertz']))>1 or a['course']!=b['course'] or abs(a['duration']-b['duration'])>.01:
            raise ValueError('A/B clips must have the same requested pitch, course and duration.')
        if secrets.randbelow(2):
            left,right=right,left
        identity=uuid.uuid4().hex
        with self.library.connect() as db:
            db.execute('INSERT INTO comparisons VALUES (?,?,?,NULL,NULL,?)',(identity,left['id'],right['id'],now()))
        return dict(id=identity,frequencyHertz=a['frequencyHertz'],course=a['course'],
                    audioA=f'/api/comparisons/{identity}/a',audioB=f'/api/comparisons/{identity}/b')

    def comparison_row(self, identity: str) -> dict:
        with self.library.connect() as db:
            row=db.execute('SELECT * FROM comparisons WHERE id=?',(identity,)).fetchone()
        if not row:
            raise KeyError('Comparison not found.')
        return dict(row)

    def prefer(self, identity: str, value: dict) -> dict:
        row=self.comparison_row(identity)
        preference=value.get('preference')
        if preference not in ('a','b','same','neither'):
            raise ValueError('Choose A, B, no preference, or neither.')
        with self.library.connect() as db:
            db.execute('UPDATE comparisons SET preference=?,note=?,updated_at=? WHERE id=?',
                       (preference,str(value.get('note','')).strip()[:1000],now(),identity))
        a,b=self.render(row['a_id']),self.render(row['b_id'])
        return dict(saved=True,methodA=a['method'],methodB=b['method'],modelA=a['model_id'],modelB=b['model_id'],preference=preference,trainingChanged=False)

    def report(self) -> dict:
        with self.library.connect() as db:
            ratings=[dict(row) for row in db.execute('SELECT * FROM ratings ORDER BY updated_at DESC')]
            comparisons=[dict(row) for row in db.execute('SELECT * FROM comparisons WHERE preference IS NOT NULL ORDER BY updated_at DESC')]
        for row in ratings:
            row['tags']=json.loads(row['tags'])
            row['render']=self.render(row['render_id'])
        wins={}
        for row in comparisons:
            a,b=self.render(row['a_id']),self.render(row['b_id'])
            row['methodA'],row['methodB']=a['method'],b['method']
            row['modelA'],row['modelB']=a['model_id'],b['model_id']
            row['hashA'],row['hashB']=a['identity'],b['identity']
            row['parametersA'],row['parametersB']=a['parameters'],b['parameters']
            row['parameters']=a['parameters']
            if row['preference'] in ('a','b'):
                method=a['method'] if row['preference']=='a' else b['method']
                wins[method]=wins.get(method,0)+1
        issues={tag:sum(tag in r['tags'] for r in ratings) for tag in TAGS}
        return dict(ratings=ratings,comparisons=comparisons,summary=dict(ratedSounds=len(ratings),
                    completedComparisons=len(comparisons),preferenceWins=wins,issueCounts=issues),
                    explanation='These are your listening preferences, not objective test labels. Nothing retrains automatically; generated clips never enter the real-recording export.')
