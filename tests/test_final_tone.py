import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import numpy as np
from baglama_sound_ml.final_tone import detect_final_tone,synthetic_strum
from baglama_sound_ml.local_server import LabApplication,make_handler


def strum(offset=0,notes=(45,55,50),rate=48000,reference=440):
    t=np.arange(rate*2)/rate;x=np.zeros(len(t))
    for onset,midi in zip([.1,.18,.26],notes):
        age=np.maximum(t-onset,0);env=(t>=onset)*np.minimum(age*150,1)*np.exp(-3*age)
        hz=reference*2**((midi+offset-69)/12)
        for harmonic in range(1,7):x+=env*np.sin(2*np.pi*hz*harmonic*t+.13*harmonic)/harmonic**1.4
    return (x/max(np.max(np.abs(x)),1)*.7).astype('<f4')


class FinalToneTests(unittest.TestCase):
    def test_transposed_strums_find_all_twelve_final_tones(self):
        for offset in range(-2,10):
            with self.subTest(offset=offset):
                result=detect_final_tone(strum(offset),48000)
                self.assertEqual(result['status'],'detected',result)
                self.assertEqual(result['finalTone']['pitchClass'],(9+offset)%12)
                self.assertEqual(len(result['courses']),3)
    def test_single_course_missing_course_silence_and_noise_abstain(self):
        rng=np.random.default_rng(7)
        for audio in [np.zeros(96000),strum(notes=(45,)),strum(notes=(45,55)),rng.normal(0,.1,96000),strum(notes=(45,49,52))]:
            self.assertEqual(detect_final_tone(audio,48000)['status'],'insufficient')
    def test_reference_rate_levels_and_input_immutability(self):
        for rate in [16000,44100,48000]:
            audio=strum(offset=1,rate=rate,reference=442);original=audio.copy()
            result=detect_final_tone(audio,rate,442)
            self.assertEqual(result['finalTone']['pitchClass'],10)
            np.testing.assert_array_equal(audio,original)
        audio=strum()*.04
        self.assertEqual(detect_final_tone(audio,48000)['finalTone']['pitchClass'],9)
    def test_clear_but_detuned_pattern_is_only_a_possible_final_tone(self):
        good=detect_final_tone(strum(),48000)
        self.assertEqual(good['tuningStatus'],'inTune')
        shifted=detect_final_tone(strum(reference=440*2**(18/1200)),48000)
        self.assertEqual(shifted['finalTone']['pitchClass'],9)
        self.assertEqual(shifted['tuningStatus'],'needsTuning')
        self.assertTrue(any(not c['inTune'] for c in shifted['courses']))

    def test_bad_audio_and_reference_are_rejected(self):
        for audio,rate,reference in [(np.zeros(10),48000,440),(np.zeros(48000),48000,float('nan')),(np.full(48000,float('nan')),48000,440),(np.ones(48000),48000.5,440),(np.zeros(48000),48000,500)]:
            with self.assertRaises(ValueError):detect_final_tone(audio,rate,reference)
    def test_demo_api_is_authenticated_and_does_not_save_samples_or_renders(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);app=LabApplication(root,root/'library',root/'absent.npz')
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            address=f'http://127.0.0.1:{server.server_port}'
            try:
                def request(body,token):
                    return urlopen(Request(address+'/api/final-tone',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':address,'X-Baglama-Token':token}))
                with self.assertRaises(HTTPError) as error:request({'demo':True},'wrong')
                self.assertEqual(error.exception.code,403)
                with request({'demo':True,'referenceHertz':440},app.token) as response:self.assertEqual(json.load(response)['finalTone']['pitchClass'],9)
                audio,rate=synthetic_strum()
                with request(dict(audio=base64.b64encode(audio.tobytes()).decode(),sampleRate=rate),app.token) as response:self.assertEqual(json.load(response)['status'],'detected')
                self.assertEqual(app.samples(),[]);self.assertEqual(app.feedback.renders(),[])
            finally:server.shutdown();thread.join();server.server_close()
