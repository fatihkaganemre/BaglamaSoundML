"""Local real-recording library with saved trims and recoverable Trash."""
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
                CREATE TABLE IF NOT EXISTS trimmed_audio (
                  sample_id TEXT PRIMARY KEY REFERENCES samples(id), pcm BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS trimmed_identities (
                  identity TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES samples(id));
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
            for row in db.execute('SELECT sample_id FROM trimmed_audio'):
                # Finish cleanup if a previous process exited after committing the trim.
                (self.root/'originals'/f'{row["sample_id"]}.f32').unlink(missing_ok=True)

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
        if analysis is not None and not isinstance(analysis,dict):
            raise ValueError('Pitch analysis must be an object.')
        result = analysis if analysis is not None else analyze_capture(audio, rate)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('''SELECT id,deleted_at FROM samples WHERE identity=?
                                     UNION ALL
                                     SELECT samples.id,samples.deleted_at FROM trimmed_identities
                                     JOIN samples ON samples.id=trimmed_identities.sample_id
                                     WHERE trimmed_identities.identity=?''',(identity,identity)).fetchone()
            if existing:
                if existing['deleted_at']:
                    raise ValueError('This recording is already in Trash. Restore it in the library.')
                return dict(id=existing['id'], duplicate=True)
            if db.execute('SELECT 1 FROM samples WHERE id=?',(sample_id,)).fetchone():
                sample_id = uuid.uuid4().hex
            path = self.root/'originals'/f'{sample_id}.f32'
            temporary = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_bytes(raw)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            db.execute('INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',
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
            return self._sample_rows(db, trash)

    def _sample_rows(self, db, trash: bool) -> list[dict]:
        rows = db.execute('''SELECT samples.*, sample_edits.start_frame, sample_edits.end_frame,
                             sample_edits.analysis AS trim_analysis FROM samples
                             LEFT JOIN sample_edits ON sample_edits.sample_id=samples.id
                             WHERE deleted_at IS '''+('NOT NULL' if trash else 'NULL')+
                          ' ORDER BY created_at DESC,id').fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            item['label']=json.loads(item['label'])
            item['analysis']=json.loads(item['analysis'])
            item['originalFrames']=item['frames']
            start, end = item.pop('start_frame'), item.pop('end_frame')
            analysis = item.pop('trim_analysis')
            item['startFrame']=start if start is not None else 0
            item['endFrame']=end if end is not None else item['frames']
            if analysis is not None:
                item['analysis']=json.loads(analysis)
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
        audio, row = self.sample_audio(sample_id, original)
        return audio, row['rate']

    def sample_audio(self, sample_id: str, original: bool = False) -> tuple[np.ndarray, dict]:
        with self.connect() as db:
            db.execute('BEGIN')
            return self._read_sample_audio(db, sample_id, original)

    def _read_sample_audio(self, db, sample_id: str, original: bool) -> tuple[np.ndarray, dict]:
        row = db.execute('''SELECT samples.*, sample_edits.start_frame, sample_edits.end_frame,
                            sample_edits.analysis AS trim_analysis, trimmed_audio.pcm FROM samples
                            LEFT JOIN sample_edits ON sample_edits.sample_id=samples.id
                            LEFT JOIN trimmed_audio ON trimmed_audio.sample_id=samples.id
                            WHERE samples.id=?''', (sample_id,)).fetchone()
        if row is None:
            raise KeyError('Sample not found.')
        metadata = dict(row)
        raw = metadata.pop('pcm')
        if raw is None:
            raw = (self.root/'originals'/f'{sample_id}.f32').read_bytes()
        audio = np.frombuffer(raw, dtype='<f4').astype(np.float64)
        if not original and row['start_frame'] is not None:
            audio = audio[row['start_frame']:row['end_frame']]
        return audio, metadata

    def trim(self, sample_id: str, start: int, end: int, expected_identity: str | None = None) -> dict:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            audio, row = self._read_sample_audio(db, sample_id, original=True)
            if row['deleted_at']:
                raise ValueError('Restore this sample before editing it.')
            if expected_identity is not None and expected_identity != row['identity']:
                raise ValueError('This sample changed. Reopen the editor before saving.')
            rate = row['rate']
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(audio) or end-start < rate*.2:
                raise ValueError('Select at least 0.20 seconds within the stored sample.')
            selected = audio[start:end]
            raw = selected.astype('<f4').tobytes()
            identity = hashlib.sha256(raw).hexdigest()
            if db.execute('''SELECT 1 FROM samples WHERE identity=? AND id<>?
                             UNION ALL
                             SELECT 1 FROM trimmed_identities WHERE identity=? AND sample_id<>?''',
                          (identity,sample_id,identity,sample_id)).fetchone():
                raise ValueError('This selection matches an existing recording in the library or Trash.')
            changed = identity != row['identity']
            if changed:
                db.execute('PRAGMA secure_delete=ON')
                db.execute('INSERT OR IGNORE INTO trimmed_identities VALUES (?,?)', (row['identity'],sample_id))
                db.execute('INSERT OR REPLACE INTO trimmed_audio VALUES (?,?)', (sample_id,raw))
                db.execute('UPDATE samples SET identity=?, frames=?, analysis=? WHERE id=?',
                           (identity,len(selected),json.dumps(analyze_capture(selected,rate)),sample_id))
            db.execute('DELETE FROM sample_edits WHERE sample_id=?', (sample_id,))
        if changed:
            (self.root/'originals'/f'{sample_id}.f32').unlink(missing_ok=True)
        return dict(saved=True,startFrame=0,endFrame=end-start,identity=identity)

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
        with self.connect() as db, zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as pack:
            db.execute('BEGIN')
            for row in self._sample_rows(db, trash=False):
                prefix=f'Samples/{row["id"]}'
                audio,_=self._read_sample_audio(db,row['id'],original=False)
                pack.writestr(prefix+'.f32',audio.astype('<f4').tobytes())
                pack.writestr(prefix+'.json',json.dumps(dict(id=row['id'],sampleRate=row['rate'],
                    audioFormat='pcm_f32le_mono',duration=row['duration'],label=row['label'],
                    pitchAnalysis=row['analysis'],sessionID=row['session'])))
        return output.getvalue()
