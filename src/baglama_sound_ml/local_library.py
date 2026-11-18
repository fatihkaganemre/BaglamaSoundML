"""Local real-recording archive. Original audio is retained; removal is recoverable."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import io
import json
import sqlite3
import zipfile
import uuid
import numpy as np
from .audio import finish, RATE, write_wav
from .capture_analysis import analyze_capture


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalLibrary:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ('originals','renders'):
            (self.root/name).mkdir(exist_ok=True)
        self.database = self.root/'library.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS samples (
                  id TEXT PRIMARY KEY, identity TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
                  analysis TEXT NOT NULL, rate INTEGER NOT NULL, frames INTEGER NOT NULL,
                  source TEXT NOT NULL, detail TEXT NOT NULL, session TEXT NOT NULL,
                  created_at TEXT NOT NULL, deleted_at TEXT);
                CREATE TABLE IF NOT EXISTS sample_edits (sample_id TEXT PRIMARY KEY REFERENCES samples(id), start_frame INTEGER NOT NULL, end_frame INTEGER NOT NULL, analysis TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS renders (
                  id TEXT PRIMARY KEY, identity TEXT NOT NULL, parameters TEXT NOT NULL,
                  model_id TEXT NOT NULL, method TEXT NOT NULL, favorite INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL, deleted_at TEXT);
                CREATE TABLE IF NOT EXISTS ratings (
                  render_id TEXT PRIMARY KEY REFERENCES renders(id), naturalness INTEGER NOT NULL,
                  attack INTEGER NOT NULL, decay INTEGER NOT NULL, pitch_impression TEXT NOT NULL,
                  tags TEXT NOT NULL, note TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS comparisons (
                  id TEXT PRIMARY KEY, a_id TEXT NOT NULL REFERENCES renders(id),
                  b_id TEXT NOT NULL REFERENCES renders(id), preference TEXT,
                  note TEXT, updated_at TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_real(self, audio: np.ndarray, rate: int, label: dict, source: str,
                 detail: str = '', session: str = '', analysis: dict | None = None) -> dict:
        if not 8000 <= rate <= 192000 or audio.ndim != 1 or not rate*0.2 <= len(audio) <= rate*30:
            raise ValueError('A sample must contain 0.2–30 seconds of mono audio at 8–192 kHz.')
        if not np.all(np.isfinite(audio)) or np.max(np.abs(audio)) > 1.01:
            raise ValueError('Audio contains invalid sample values.')
        raw = audio.astype('<f4').tobytes()
        identity = hashlib.sha256(raw).hexdigest()
        sample_id = identity[:32]
        with self.connect() as db:
            existing = db.execute('SELECT id,deleted_at FROM samples WHERE identity=?',(identity,)).fetchone()
            if existing:
                if existing['deleted_at']:
                    raise ValueError('This recording is already in Trash. Restore it in the library.')
                return dict(id=existing['id'], duplicate=True)
        if analysis is not None and not isinstance(analysis,dict):
            raise ValueError('Pitch analysis must be an object.')
        result = analysis if analysis is not None else analyze_capture(audio, rate)
        path = self.root/'originals'/f'{sample_id}.f32'
        temporary = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        temporary.write_bytes(raw)
        temporary.replace(path)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',
                       (sample_id, identity, json.dumps(label), json.dumps(result), rate, len(audio), source,
                        detail[:200], session[:100], now()))
        return dict(id=sample_id, duplicate=False)

    def import_archive(self, content, name: str) -> dict:
        added = duplicates = 0
        with zipfile.ZipFile(content) as pack:
            names = set(pack.namelist())
            if len(names)>10000 or sum(item.file_size for item in pack.infolist())>512*1024*1024:
                raise ValueError('Import one sample pack smaller than 512 MB expanded at a time.')
            for filename in sorted(names):
                if not filename.endswith('.json') or filename.startswith('__MACOSX/'):
                    continue
                if pack.getinfo(filename).file_size > 1_000_000:
                    raise ValueError('Sample metadata is too large.')
                metadata = json.loads(pack.read(filename))
                if not isinstance(metadata,dict):
                    raise ValueError('Sample metadata must be a JSON object.')
                if metadata.get('audioFormat') != 'pcm_f32le_mono':
                    continue
                audio_name = str(Path(filename).with_suffix('.f32'))
                if audio_name not in names:
                    continue
                if pack.getinfo(audio_name).file_size > 192000*4*30:
                    raise ValueError('A recording exceeds the import limit.')
                audio = np.frombuffer(pack.read(audio_name), dtype='<f4')
                label = metadata.get('label', {})
                if not isinstance(label,dict) or not isinstance(label.get('target'),dict) or type(label['target'].get('note')) is not int or not 0<=label['target']['note']<=11:
                    raise ValueError('A capture is missing its note label.')
                # Include uncertain recordings too: library review is independent of training admission.
                try:
                    row = self.add_real(audio, int(metadata['sampleRate']), label, 'Baglamator ZIP',
                                        name, str(metadata.get('sessionID',name)), metadata.get('pitchAnalysis'))
                    added += int(not row['duplicate'])
                    duplicates += int(row['duplicate'])
                except ValueError as error:
                    if 'already in Trash' in str(error):
                        duplicates += 1
                    else:
                        raise
        return dict(added=added, duplicates=duplicates)

    def import_folder(self, source: Path) -> dict:
        totals = dict(added=0, duplicates=0)
        for path in sorted(source.rglob('*.zip')) if source.exists() else []:
            result = self.import_archive(path, path.name)
            for key in totals:
                totals[key] += result[key]
        return totals

    def samples(self, trash: bool = False) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('SELECT * FROM samples WHERE deleted_at IS '+('NOT NULL' if trash else 'NULL')+' ORDER BY created_at DESC,id').fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            item['label']=json.loads(item['label'])
            item['analysis']=json.loads(item['analysis'])
            item['originalFrames']=item['frames']
            with self.connect() as db:
                edit=db.execute('SELECT * FROM sample_edits WHERE sample_id=?',(item['id'],)).fetchone()
            item['startFrame']=edit['start_frame'] if edit else 0
            item['endFrame']=edit['end_frame'] if edit else item['frames']
            if edit:
                item['analysis']=json.loads(edit['analysis'])
            item['frames']=item['endFrame']-item['startFrame']
            item['duration']=item['frames']/item['rate']
            item['kind']='real'
            result.append(item)
        return result

    def sample(self, sample_id: str) -> dict:
        with self.connect() as db:
            row=db.execute('SELECT * FROM samples WHERE id=?',(sample_id,)).fetchone()
        if not row:
            raise KeyError('Sample not found.')
        return dict(row)

    def real_audio(self, sample_id: str, original: bool = False) -> tuple[np.ndarray, int]:
        row=self.sample(sample_id)
        audio=np.frombuffer((self.root/'originals'/f'{row["id"]}.f32').read_bytes(),dtype='<f4').astype(np.float64)
        if not original:
            with self.connect() as db:
                edit=db.execute('SELECT * FROM sample_edits WHERE sample_id=?',(sample_id,)).fetchone()
            if edit:
                audio=audio[edit['start_frame']:edit['end_frame']]
        return audio,row['rate']

    def trim(self, sample_id: str, start: int, end: int) -> dict:
        row=self.sample(sample_id)
        if row['deleted_at']:
            raise ValueError('Restore this sample before editing it.')
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= row['frames'] or end-start < row['rate']*.2:
            raise ValueError('Select at least 0.20 seconds within the original sample.')
        audio,rate=self.real_audio(sample_id,original=True)
        analysis=analyze_capture(audio[start:end],rate)
        with self.connect() as db:
            if start==0 and end==row['frames']:
                db.execute('DELETE FROM sample_edits WHERE sample_id=?',(sample_id,))
            else:
                db.execute('INSERT OR REPLACE INTO sample_edits VALUES (?,?,?,?)',(sample_id,start,end,json.dumps(analysis)))
        return dict(saved=True,startFrame=start,endFrame=end)

    def trash(self, kind: str, identity: str, restore: bool = False):
        table='samples' if kind=='samples' else 'renders' if kind=='renders' else None
        if table is None:
            raise ValueError('Unknown library type.')
        with self.connect() as db:
            changed=db.execute(f'UPDATE {table} SET deleted_at=? WHERE id=?',(None if restore else now(),identity)).rowcount
            if not changed:
                raise KeyError('Item not found.')

    def export_real(self) -> bytes:
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as pack:
            for row in self.samples():
                prefix=f'Samples/{row["id"]}'
                audio,_=self.real_audio(row['id'])
                pack.writestr(prefix+'.f32',audio.astype('<f4').tobytes())
                pack.writestr(prefix+'.json',json.dumps(dict(id=row['id'],sampleRate=row['rate'],
                    audioFormat='pcm_f32le_mono',duration=row['duration'],label=row['label'],
                    pitchAnalysis=row['analysis'],sessionID=row['session'])))
        return output.getvalue()
