"""Owner-labeled, local strum evaluation cases; never part of synthesis training."""
from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
import hashlib
import io
import json
import sqlite3
import uuid
import zipfile
import numpy as np
from .local_library import now
from .final_tone import detect_final_tone
from .strum_labels import validate_string_labels

VERSION='final-tone-spectrum-v1.1'


class FinalToneCases:
    def __init__(self, root: Path):
        self.root=root.resolve();(self.root/'audio').mkdir(parents=True,exist_ok=True)
        self.database=self.root/'cases.sqlite3'
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY, rate INTEGER NOT NULL, frames INTEGER NOT NULL,
                reference REAL NOT NULL, expected INTEGER NOT NULL, tuning TEXT NOT NULL,
                notes TEXT NOT NULL, source TEXT NOT NULL, prediction TEXT NOT NULL,
                detector_version TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                deleted_at TEXT)''')
            if 'instrument_details' not in {row['name'] for row in db.execute('PRAGMA table_info(cases)')}:
                db.execute("ALTER TABLE cases ADD COLUMN instrument_details TEXT NOT NULL DEFAULT '{}'")

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.database,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def save(self,audio,rate,reference,body):
        if body.get('confirmedReal') is not True:
            raise ValueError('Confirm this is a real open-string strum and explicitly allow saving its audio.')
        expected=body.get('expectedPitchClass');tuning=body.get('knownTuning','unknown')
        if type(expected) is not int or not 0<=expected<=11:
            raise ValueError('Choose the known final tone independently of the detector guess.')
        details=validate_string_labels(body,expected)
        if tuning not in ('inTune','needsTuning','unknown'):
            raise ValueError('Choose tuned, needs tuning, or unknown.')
        if body.get('source') not in ('microphone','WAV'):
            raise ValueError('Only real microphone/WAV strums can be saved, not the synthetic demo.')
        # Also validates PCM/rate/reference and stores the exact current detector result.
        prediction=detect_final_tone(audio,rate,reference)
        raw=np.asarray(audio,dtype='<f4').tobytes()
        identity=hashlib.sha256(str(rate).encode()+b':'+raw).hexdigest()
        timestamp=now();notes=str(body.get('notes','')).strip()[:500]
        with self.connect() as db:
            old=db.execute('SELECT * FROM cases WHERE id=?',(identity,)).fetchone()
            if old:
                if old['deleted_at']:raise ValueError('This strum is already in test-case Trash. Restore it first.')
                if abs(old['reference']-reference)>.0001:raise ValueError('This audio is already saved with another reference pitch. Use its original reference.')
                db.execute('UPDATE cases SET expected=?,tuning=?,notes=?,updated_at=?,instrument_details=? WHERE id=?',(expected,body.get('knownTuning',old['tuning']),notes,timestamp,json.dumps(details or json.loads(old['instrument_details'])),identity))
                return dict(id=identity,duplicate=True,saved=True)
            path=self.root/'audio'/(identity+'.f32');temporary=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
            temporary.write_bytes(raw);temporary.replace(path)
            db.execute('INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)',(identity,rate,len(audio),reference,expected,tuning,notes,body['source'],json.dumps(prediction),VERSION,timestamp,timestamp,json.dumps(details)))
        return dict(id=identity,duplicate=False,saved=True)

    def rows(self,trash=False):
        with self.connect() as db:
            rows=db.execute('SELECT * FROM cases WHERE deleted_at IS '+('NOT NULL' if trash else 'NULL')+' ORDER BY created_at DESC,id').fetchall()
        result=[]
        for row in rows:
            item=dict(row);item['prediction']=json.loads(item['prediction']);item['duration']=item['frames']/item['rate'];item['instrumentDetails']=json.loads(item.pop('instrument_details'));result.append(item)
        return result

    def audio(self,identity):
        with self.connect() as db:row=db.execute('SELECT id,rate FROM cases WHERE id=?',(identity,)).fetchone()
        if not row:raise KeyError('Test case not found.')
        return np.frombuffer((self.root/'audio'/(row['id']+'.f32')).read_bytes(),dtype='<f4'),row['rate']

    def trash(self,identity,restore=False):
        with self.connect() as db:
            if not db.execute('UPDATE cases SET deleted_at=? WHERE id=?',(None if restore else now(),identity)).rowcount:raise KeyError('Test case not found.')
        return dict(saved=True)

    def export(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as pack:
            rows=self.rows();pack.writestr('README.txt','Owner-labeled development evaluation strums. Not an independent final test set if used to tune the detector. Not synthesis training data. PCM is float32 little-endian mono.\n')
            for row in rows:
                audio,_=self.audio(row['id']);pack.writestr('cases/'+row['id']+'.f32',audio.astype('<f4').tobytes());pack.writestr('cases/'+row['id']+'.json',json.dumps(row,indent=2))
        return output.getvalue()

    def evaluate(self):
        cases=[];unsupported=[]
        for row in self.rows():
            details=row['instrumentDetails']
            if details and (details['instrumentID']!='kisaSap' or details['tuningID']!='baglama'):
                unsupported.append(dict(id=row['id'],reason='Detector currently supports Kısa Sap / Bağlama Düzeni only.',instrumentDetails=details));continue
            audio,rate=self.audio(row['id']);result=detect_final_tone(audio,rate,row['reference']);predicted=result['finalTone']['pitchClass'] if result['finalTone'] else None
            cases.append(dict(id=row['id'],expected=row['expected'],predicted=predicted,correct=predicted==row['expected'],result=result,instrumentDetails=details,knownTuning=row['tuning'],tuningCorrect=(result['tuningStatus']==row['tuning']) if row['tuning']!='unknown' else None))
        detected=sum(c['predicted'] is not None for c in cases);correct=sum(c['correct'] for c in cases)
        tuning_labeled=[c for c in cases if c['tuningCorrect'] is not None]
        return dict(unsupported=unsupported,unsupportedCount=len(unsupported),tuningLabeled=len(tuning_labeled),tuningAccuracyWhenLabeled=sum(c['tuningCorrect'] for c in tuning_labeled)/len(tuning_labeled) if tuning_labeled else None,detectorVersion=VERSION,total=len(cases),detected=detected,abstained=len(cases)-detected,correct=correct,accuracyIncludingAbstentions=correct/len(cases) if cases else None,accuracyWhenDetected=correct/detected if detected else None,cases=cases,caveat='Owner-labeled development evaluation, not an independent final test if these examples informed detector improvements. Exact PCM duplicates are deduplicated; related takes can still be correlated.')
