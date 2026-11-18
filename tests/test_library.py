import base64
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
from baglama_sound_ml.local_library import LocalLibrary
from baglama_sound_ml.feedback_store import FeedbackStore
from baglama_sound_ml.local_server import LabApplication
from baglama_sound_ml.capture_catalog import validate_label


def tone(hz=110,seconds=.8):
    times=np.arange(round(48000*seconds))/48000
    return (.2*np.sin(2*np.pi*hz*times)*np.exp(-times)).astype('<f4')


def label():
    return dict(instrumentID='kisaSap',tuningID='baglama',variantID='karar-A',
                stringID='kisaSap.baglama.ust.1',referenceHertz=440)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.app=LabApplication(self.root,self.root/'library',self.root/'absent-model.npz')
    def tearDown(self):
        self.temp.cleanup()
    def add(self,audio=None):
        audio=tone() if audio is None else audio
        return self.app.add_recording(dict(label=label(),audio=base64.b64encode(audio.tobytes()).decode(),
            sampleRate=48000,source='WAV upload',confirmedReal=True,session='independent-session',pluckStrength='soft'))

    def test_original_pcm_persists_and_analysis_does_not_follow_target(self):
        original=tone(196)
        saved=self.add(original)
        actual,rate=self.app.library.real_audio(saved['id'])
        self.assertTrue(np.array_equal(actual,original.astype(np.float64)))
        row=self.app.samples()[0]
        self.assertAlmostEqual(row['analysis']['estimatedFrequencyHertz'],196,delta=.3)
        self.assertEqual(row['label']['target']['note'],9)
        self.assertEqual(row['label']['pluckStrength'],'soft')
        self.assertEqual(row['modelUsage'],'unseen')
        reloaded=LocalLibrary(self.root/'library')
        self.assertEqual(len(reloaded.samples()),1)
        self.assertEqual(rate,48000)
        self.assertTrue(self.add(original)['duplicate'])

    def test_trash_restore_and_zip_export_do_not_promote_generated_audio(self):
        saved=self.add();feedback=self.app.feedback
        generated=feedback.add_render(tone(120),dict(frequencyHertz=120,course='ust',duration=.8,seed=7),'test-model','neural')
        feedback.rate(generated['id'],dict(naturalness=2,attack=1,decay=3,pitchImpression='okay',tags=['weak-attack'],note='soft attack',favorite=True))
        self.assertEqual(len(self.app.library.samples()),1)
        with zipfile.ZipFile(io.BytesIO(self.app.library.export_real())) as archive:
            self.assertEqual(len(archive.namelist()),2)
            self.assertNotIn(generated['id'],' '.join(archive.namelist()))
        self.app.library.trash('samples',saved['id'])
        self.assertEqual(len(self.app.library.samples()),0)
        self.assertEqual(len(self.app.library.samples(True)),1)
        self.app.library.trash('samples',saved['id'],True)
        self.assertEqual(len(self.app.library.samples()),1)
        self.assertTrue((self.root/'library/originals'/f'{saved["id"]}.f32').exists())

    def test_uncertain_imports_stay_reviewable_and_do_not_resurrect_trash(self):
        buffer=io.BytesIO();meta=dict(audioFormat='pcm_f32le_mono',sampleRate=48000,label=validate_label(label()),
            pitchAnalysis=dict(quality='uncertain',estimatedFrequencyHertz=110))
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('Samples/example.json',json.dumps(meta));archive.writestr('Samples/example.f32',tone().tobytes())
        result=self.app.library.import_archive(io.BytesIO(buffer.getvalue()),'local.zip')
        self.assertEqual(result['added'],1)
        saved=self.app.library.samples()[0]
        self.assertEqual(saved['analysis']['quality'],'uncertain')
        self.app.library.trash('samples',saved['id'])
        again=self.app.library.import_archive(io.BytesIO(buffer.getvalue()),'local.zip')
        self.assertEqual(again['added'],0)
        self.assertEqual(len(self.app.library.samples()),0)

    def test_catalog_octaves_and_optional_ground_truth_are_not_invented(self):
        unknown=label();unknown.update(variantID='karar-G-sharp')
        self.assertNotIn('octave',validate_label(unknown)['target'])
        self.assertEqual(validate_label(label())['target']['octave'],2)
        invalid=label();invalid['groundTruthHertz']=110
        with self.assertRaises(ValueError):validate_label(invalid)
        invalid=label();invalid['octave']=4
        with self.assertRaises(ValueError):validate_label(invalid)
        with self.assertRaises(ValueError):
            self.app.add_recording(dict(label=label(),confirmedReal=False))
        bad=tone();bad[20]=np.nan
        with self.assertRaises(ValueError):self.add(bad)
        with self.assertRaises(KeyError):self.app.library.real_audio('../../outside')

    def test_preferences_require_comparable_distinct_outputs_and_revisions_count_once(self):
        params=dict(frequencyHertz=110,course='ust',duration=.8,seed=7)
        a=self.app.feedback.add_render(tone(),params,'model-v1','neural')
        same=self.app.feedback.add_render(tone(),params,'model-v1','neural')
        b=self.app.feedback.add_render(tone()*0.8,params,'baseline','sample')
        wrong=self.app.feedback.add_render(tone(196),dict(params,frequencyHertz=196),'baseline','sample')
        with self.assertRaises(ValueError):self.app.feedback.comparison(a['id'],same['id'])
        with self.assertRaises(ValueError):self.app.feedback.comparison(a['id'],wrong['id'])
        pair=self.app.feedback.comparison(a['id'],b['id'])
        self.assertNotIn('methodA',pair)
        revealed=self.app.feedback.prefer(pair['id'],dict(preference='a',note='clearer attack'))
        self.assertEqual({revealed['methodA'],revealed['methodB']},{'neural','sample'})
        for score in (1,4):
            self.app.feedback.rate(a['id'],dict(naturalness=score,attack=2,decay=3,pitchImpression='unsure',tags=['synthetic'],favorite=True))
        report=self.app.feedback.report()
        self.assertEqual(report['summary']['ratedSounds'],1)
        self.assertEqual(report['ratings'][0]['naturalness'],4)
        self.assertEqual(report['summary']['completedComparisons'],1)
        self.assertEqual(len(self.app.library.samples()),0)
        self.app.library.trash('renders',a['id'])
        self.assertEqual(len(self.app.feedback.renders(True)),1)
        self.app.library.trash('renders',a['id'],True)
        self.assertTrue(self.app.feedback.render(a['id'])['favorite'])
