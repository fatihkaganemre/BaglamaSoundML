import tempfile
import unittest
import sqlite3
from pathlib import Path
from baglama_sound_ml.capture_catalog import catalog
from baglama_sound_ml.strum_labels import validate_string_labels
from baglama_sound_ml.final_tone import synthetic_strum
from baglama_sound_ml.final_tone_cases import FinalToneCases


def labels(instrument='kisaSap',tuning='baglama'):
    i=next(i for i in catalog()['instruments'] if i['id']==instrument);t=next(t for t in i['tunings'] if t['id']==tuning);v=next(v for v in t['variants'] if v['kararPitchClass']==9)
    return dict(instrumentID=instrument,tuningID=tuning,strings=[dict(stringID=s['id'],note=None,octave=None,cents=None) for c in v['courses'] for s in c['strings']])

class StrumLabelTests(unittest.TestCase):
    def test_unknowns_and_signed_cents_remain_distinct_from_zero(self):
        body=labels();body['strings'][0].update(note=9,octave=2,cents=-12.5);body['strings'][1].update(note=9,octave=3,cents=0);body['strings'][2].update(note=7,cents=4)
        result=validate_string_labels(body,9)
        self.assertEqual(len(result['strings']),7);self.assertEqual(result['strings'][0]['cents'],-12.5);self.assertEqual(result['strings'][1]['cents'],0);self.assertIsNone(result['strings'][3]['cents']);self.assertIsNone(result['strings'][2]['octave'])
    def test_invalid_string_order_note_and_nonfinite_cents_are_rejected(self):
        for changes in [dict(note=True),dict(note=12),dict(octave=8),dict(note=None,cents=2),dict(note=9,cents=float('nan')),dict(note=9,cents=1201),dict(stringID='wrong')]:
            body=labels();body['strings'][0].update(changes)
            with self.assertRaises(ValueError):validate_string_labels(body,9)
        body=labels();body['strings'].pop()
        with self.assertRaises(ValueError):validate_string_labels(body,9)
    def test_save_edit_export_and_unsupported_instruments_preserve_details(self):
        with tempfile.TemporaryDirectory() as temp:
            store=FinalToneCases(Path(temp));audio,rate=synthetic_strum();body={**labels(),'confirmedReal':True,'source':'microphone','expectedPitchClass':9}
            body['strings'][0].update(note=9,octave=2,cents=-4)
            identity=store.save(audio,rate,440,body)['id'];self.assertEqual(store.rows()[0]['instrumentDetails']['strings'][0]['cents'],-4)
            body.update(labels('cura'));store.save(audio,rate,440,body);report=store.evaluate();self.assertEqual(report['unsupportedCount'],1);self.assertEqual(report['total'],0)
            self.assertEqual(store.rows()[0]['instrumentDetails']['instrumentID'],'cura')
    def test_legacy_database_migrates_without_inventing_string_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            store=FinalToneCases(Path(temp));audio,rate=synthetic_strum();store.save(audio,rate,440,dict(confirmedReal=True,source='WAV',expectedPitchClass=9))
            with store.connect() as db:db.execute('ALTER TABLE cases DROP COLUMN instrument_details')
            migrated=FinalToneCases(Path(temp));self.assertEqual(len(migrated.rows()),1);self.assertEqual(migrated.rows()[0]['instrumentDetails'],{})
