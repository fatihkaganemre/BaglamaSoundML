import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
from baglama_sound_ml.final_tone import synthetic_strum
from baglama_sound_ml.final_tone_cases import FinalToneCases
from baglama_sound_ml.local_library import LocalLibrary

class FinalToneCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=FinalToneCases(self.root/'cases')
        self.audio,self.rate=synthetic_strum();self.body=dict(confirmedReal=True,source='microphone',expectedPitchClass=9,knownTuning='inTune',notes='test fixture only')
    def tearDown(self):self.temp.cleanup()
    def test_explicit_save_retains_pcm_prediction_and_owner_label_separately(self):
        row=self.store.save(self.audio,self.rate,440,self.body);saved=self.store.rows()[0]
        np.testing.assert_array_equal(self.store.audio(row['id'])[0],self.audio)
        self.assertEqual(saved['prediction']['finalTone']['pitchClass'],9);self.assertEqual(saved['expected'],9)
        original=saved['prediction'];self.body['expectedPitchClass']=8
        duplicate=self.store.save(self.audio,self.rate,440,self.body)
        self.assertTrue(duplicate['duplicate']);self.assertEqual(len(self.store.rows()),1)
        self.assertEqual(self.store.rows()[0]['expected'],8);self.assertEqual(self.store.rows()[0]['prediction'],original)
    def test_consent_valid_label_and_real_source_are_required(self):
        for change in [dict(confirmedReal=False),dict(expectedPitchClass=None),dict(expectedPitchClass=True),dict(expectedPitchClass=12),dict(source='synthetic'),dict(knownTuning='maybe')]:
            with self.assertRaises(ValueError):self.store.save(self.audio,self.rate,440,{**self.body,**change})
        self.assertEqual(self.store.rows(),[])
    def test_evaluation_counts_wrong_predictions_and_abstentions_and_trash_is_recoverable(self):
        first=self.store.save(self.audio,self.rate,440,self.body)
        # A failed/silent take still makes a valid explicitly labeled evaluation case.
        silent=self.store.save(np.zeros(48000,dtype='<f4'),48000,440,self.body)
        report=self.store.evaluate();self.assertEqual((report['total'],report['correct'],report['abstained']),(2,1,1));self.assertEqual(report['accuracyIncludingAbstentions'],.5)
        self.store.save(self.audio,self.rate,440,{**self.body,'expectedPitchClass':8});self.assertEqual(self.store.evaluate()['correct'],0)
        self.store.trash(silent['id']);self.assertEqual(len(self.store.rows()),1);self.assertEqual(len(self.store.rows(True)),1)
        with self.assertRaises(ValueError):self.store.save(np.zeros(48000,dtype='<f4'),48000,440,self.body)
        self.store.trash(silent['id'],True);self.assertEqual(len(self.store.rows()),2)
    def test_export_is_separate_from_synthesis_training_and_excludes_trash(self):
        saved=self.store.save(self.audio,self.rate,440,self.body)
        with zipfile.ZipFile(io.BytesIO(self.store.export())) as pack:
            self.assertEqual(len(pack.namelist()),3)
            metadata=json.loads(pack.read('cases/'+saved['id']+'.json'));self.assertEqual(metadata['expected'],9)
        library=LocalLibrary(self.root/'library');self.assertEqual(library.samples(),[])
        with zipfile.ZipFile(io.BytesIO(library.export_real())) as pack:self.assertEqual(pack.namelist(),[])
        self.store.trash(saved['id'])
        with zipfile.ZipFile(io.BytesIO(self.store.export())) as pack:self.assertEqual(pack.namelist(),['README.txt'])

    def test_authenticated_api_save_replay_export_and_restore(self):
        import base64,threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from baglama_sound_ml.local_server import LabApplication,make_handler
        app=LabApplication(self.root,self.root/'library',self.root/'absent.npz')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        address=f'http://127.0.0.1:{server.server_port}'
        body={**self.body,'sampleRate':self.rate,'referenceHertz':440,'audio':base64.b64encode(self.audio.tobytes()).decode()}
        def post(path,value,token=None):
            return urlopen(Request(address+path,data=json.dumps(value).encode(),headers={'Content-Type':'application/json','Origin':address,'X-Baglama-Token':token or app.token}))
        try:
            with self.assertRaises(HTTPError) as error:post('/api/final-tone-tests',body,'wrong')
            self.assertEqual(error.exception.code,403)
            with post('/api/final-tone-tests',body) as response:identity=json.load(response)['id']
            with urlopen(address+'/api/final-tone-tests') as response:self.assertEqual(len(json.load(response)['cases']),1)
            with urlopen(address+'/api/final-tone-tests/'+identity+'/pcm') as response:self.assertEqual(base64.b64decode(json.load(response)['audio']),self.audio.tobytes())
            with urlopen(address+'/api/final-tone-tests/'+identity+'/audio') as response:self.assertEqual(response.read()[:4],b'RIFF')
            with urlopen(address+'/api/final-tone-tests/export') as response:
                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:self.assertEqual(len(archive.namelist()),3)
            with post('/api/final-tone-tests/'+identity+'/trash',{}):pass
            with urlopen(address+'/api/final-tone-tests?trash=1') as response:self.assertEqual(len(json.load(response)['cases']),1)
            with post('/api/final-tone-tests/'+identity+'/restore',{}):pass
            self.assertEqual(app.library.samples(),[])
        finally:server.shutdown();thread.join();server.server_close()
