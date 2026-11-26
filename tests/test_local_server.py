import json
import base64
import io
import zipfile
import numpy as np
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from baglama_sound_ml.local_server import LabApplication,make_handler


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.project=root
        self.app=LabApplication(root,root/'library',root/'absent.npz')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.temp.cleanup()
    def post(self,path,body,token=None,origin=None):
        return urlopen(Request(self.url+path,data=json.dumps(body).encode(),headers={
            'Content-Type':'application/json','X-Baglama-Token':token or self.app.token,
            'Origin':origin or self.url}))
    def test_existing_read_views_and_browser_assets_load_without_microphone(self):
        for route in ('/','/lab.js','/capture-ui.js','/lab-audio.js','/capture-worklet.js','/lab.css','/api/config','/api/samples','/api/feedback'):
            with urlopen(self.url+route) as response:self.assertEqual(response.status,200)
    def test_cross_origin_or_missing_token_cannot_mutate_local_library(self):
        for token,origin in (('wrong',self.url),(self.app.token,'https://example.com')):
            with self.assertRaises(HTTPError) as result:self.post('/api/recordings',{},token,origin)
            self.assertEqual(result.exception.code,403)
        self.assertEqual(self.app.library.samples(),[])
    def test_invalid_recording_and_missing_model_return_actionable_errors(self):
        for route,body in (('/api/recordings',{}),('/api/continuations',{}),('/api/renders',dict(method='neural',frequencyHertz=110,course='ust',duration=.8))):
            with self.assertRaises(HTTPError) as result:self.post(route,body)
            self.assertEqual(result.exception.code,400)
            self.assertIn('error',json.loads(result.exception.read()))

    def test_complete_local_save_play_trash_restore_and_rating_export_flow(self):
        times=np.arange(48000)/48000
        audio=(.2*np.sin(2*np.pi*110*times)).astype('<f4')
        label=dict(instrumentID='kisaSap',tuningID='baglama',variantID='karar-A',stringID='kisaSap.baglama.ust.1')
        label['target']={'note':9,'octave':2}
        pack=io.BytesIO()
        with zipfile.ZipFile(pack,'w') as archive:
            archive.writestr('take.f32',audio.tobytes())
            archive.writestr('take.json',json.dumps(dict(audioFormat='pcm_f32le_mono',sampleRate=48000,label=label)))
        with self.post('/api/import',dict(filename='test.zip',archive=base64.b64encode(pack.getvalue()).decode())) as response:
            self.assertEqual(json.load(response)['added'],1)
        sample=self.app.samples()[0]
        with self.app.library.connect() as db:
            db.execute('INSERT INTO sample_edits VALUES (?,?,?,?)',
                       (sample['id'],4800,24000,json.dumps(sample['analysis'])))
        editor_url=self.url+'/api/samples/'+sample['id']+'/original'
        with urlopen(editor_url) as response:
            before=json.load(response)
        self.assertEqual((before['startFrame'],before['endFrame']),(4800,24000))
        with self.post('/api/samples/'+sample['id']+'/trim',dict(startFrame=4800,endFrame=24000,
                                                              expectedIdentity=before['identity'])) as response:
            saved=json.load(response)
            self.assertTrue(saved['saved'])
            self.assertEqual((saved['startFrame'],saved['endFrame']),(0,19200))
        self.assertEqual(self.app.samples()[0]['frames'],19200)
        np.testing.assert_array_equal(self.app.library.real_audio(sample['id'])[0],audio[4800:24000])
        self.assertFalse((self.project/'library'/'originals'/f'{sample["id"]}.f32').exists())
        with urlopen(editor_url) as response:
            after=json.load(response)
        self.assertEqual((after['startFrame'],after['endFrame']),(0,19200))
        self.assertNotEqual(after['identity'],before['identity'])
        self.assertEqual(saved['identity'],after['identity'])
        self.assertEqual(base64.b64decode(after['audio']),audio[4800:24000].tobytes())
        with self.post('/api/import',dict(filename='test.zip',archive=base64.b64encode(pack.getvalue()).decode())) as response:
            self.assertEqual(json.load(response),dict(added=0,duplicates=1))
        with self.assertRaises(HTTPError) as stale:
            self.post('/api/samples/'+sample['id']+'/trim',dict(startFrame=0,endFrame=12000,
                                                              expectedIdentity=before['identity']))
        self.assertEqual(stale.exception.code,400)
        with self.assertRaises(HTTPError) as outside:
            self.post('/api/samples/'+sample['id']+'/trim',dict(startFrame=0,endFrame=48000))
        self.assertEqual(outside.exception.code,400)
        with urlopen(self.url+'/api/samples/'+sample['id']+'/audio') as response:
            wav=response.read()
            self.assertEqual(wav[:4],b'RIFF')
        with self.post('/api/samples/'+sample['id']+'/trash',{}):pass
        self.assertEqual(len(self.app.samples()),0)
        with self.post('/api/samples/'+sample['id']+'/restore',{}):pass
        self.assertEqual(len(self.app.samples()),1)
        generated=self.app.feedback.add_render(audio*.8,dict(frequencyHertz=110,course='ust',duration=1,seed=7),'synthetic-test-model','neural')
        with self.post('/api/renders/'+generated['id']+'/feedback',dict(naturalness=3,attack=2,decay=4,pitchImpression='unsure',tags=['weak-attack'],note='test fixture',favorite=True)) as response:
            self.assertFalse(json.load(response)['trainingChanged'])
        with urlopen(self.url+'/api/export/feedback') as response:
            self.assertEqual(json.load(response)['summary']['ratedSounds'],1)
        with urlopen(self.url+'/api/export/samples') as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertEqual(len(archive.namelist()),2)
                self.assertNotIn(generated['id'],' '.join(archive.namelist()))
                self.assertEqual(archive.read(f'Samples/{sample["id"]}.f32'),audio[4800:24000].tobytes())

    def test_project_specific_stop_command_shuts_down_only_its_server(self):
        from baglama_sound_ml.local_server import stop_server
        stop_server(self.project,self.server.server_port)
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def test_static_generated_reports_are_served_only_within_outputs(self):
        output=self.project/'outputs';output.mkdir()
        (output/'report.html').write_text('<title>Local report</title>')
        (self.project/'private.json').write_text('{"private":true}')
        with urlopen(self.url+'/report.html') as response:
            self.assertIn(b'Local report',response.read())
        with self.assertRaises(HTTPError):
            urlopen(self.url+'/%2e%2e/private.json')
