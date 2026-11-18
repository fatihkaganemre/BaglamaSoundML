import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from baglama_sound_ml.feedback_training import plan_feedback,frame_weights,feedback_comparison
from baglama_sound_ml.neural import train,load_model,predict
from baglama_sound_ml.audio import write_wav,RATE
from baglama_sound_ml.local_library import LocalLibrary
from baglama_sound_ml.feedback_store import FeedbackStore


def clip(hz=110,course='ust',method='neural'):
    return dict(id='clip',model_id='old-model',method=method,deleted_at=None,parameters=dict(frequencyHertz=hz,course=course,duration=.5,seed=7))


def rating(render=None,**changes):
    result=dict(render_id='clip',render=render or clip(),naturalness=5,attack=1,decay=5,tags=['weak-attack'])
    result.update(changes);return result


class FeedbackTrainingTests(unittest.TestCase):
    def setUp(self):
        self.rows=[dict(identity='train',course='ust',frequency_hz=110)]
        self.held=[dict(identity='held',course='ust',frequency_hz=103.8)]
    def test_focus_is_local_bounded_and_targets_only_training_audio(self):
        report=dict(ratings=[rating()]*10)
        plan=plan_feedback(report,self.rows,self.held)
        weights=frame_weights(self.rows[0],np.array([0,.1,.2,.8]),plan)
        np.testing.assert_array_equal(weights,[2,2,1,1])
        other=dict(identity='different',course='alt',frequency_hz=110)
        np.testing.assert_array_equal(frame_weights(other,np.array([0,.5]),plan),[1,1])
        self.assertEqual(plan['focuses'][0]['realTrainingIdentities'],['train'])
    def test_validation_feedback_and_trashed_clips_do_not_affect_training(self):
        render=clip(103.8)
        plan=plan_feedback(dict(ratings=[rating(render)]),self.rows,self.held)
        self.assertEqual(plan['focuses'],[])
        self.assertIn('held-out',plan['ignored'][0]['reason'])
        render=clip();render['deleted_at']='yesterday'
        self.assertEqual(plan_feedback(dict(ratings=[rating(render)]),self.rows,self.held)['focuses'],[])
    def test_positive_feedback_is_regression_only_and_pairs_focus_neural_loser(self):
        good=rating(attack=5,tags=[])
        self.assertFalse(plan_feedback(dict(ratings=[good]),self.rows,[])['focuses'])
        pair=dict(id='pair',a_id='sample',b_id='clip',preference='a')
        plan=plan_feedback(dict(comparisons=[pair],comparisonRenders={'clip':clip()}),self.rows,[])
        self.assertEqual(plan['focuses'][0]['overall'],.5)
        pair['preference']='b'
        self.assertFalse(plan_feedback(dict(comparisons=[pair],comparisonRenders={'sample':clip(method='sample')}),self.rows,[])['focuses'])
    def test_real_training_changes_with_feedback_and_builds_replay_report(self):
        try:import torch
        except ImportError:self.skipTest('optional PyTorch is not installed')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rows=[]
            for i,(course,hz,variant) in enumerate([('ust',110,'train'),('orta',196,'train'),('alt',146.8,'train'),('ust',103.8,'held')]):
                audio=.2*np.sin(2*np.pi*hz*np.arange(RATE//2)/RATE)*np.exp(-np.arange(RATE//2)/RATE*3)
                write_wav(root/f'{i}.wav',audio)
                rows.append(dict(identity=str(i),file=f'{i}.wav',course=course,frequency_hz=hz,variant=variant))
            (root/'manifest.json').write_text(json.dumps(dict(recordings=rows)))
            baseline=train(root,root/'base.npz',10,'held',7)
            guided=train(root,root/'guided.npz',10,'held',7,dict(ratings=[rating()]))
            self.assertEqual(guided['training_identities'],baseline['training_identities'])
            self.assertGreater(guided['feedback_training']['weighted_frames'],0)
            a,_=load_model(root/'base.npz');b,_=load_model(root/'guided.npz')
            self.assertFalse(np.array_equal(a['4.weight'],b['4.weight']))
            self.assertFalse(set(guided['training_identities']) & set(guided['validation_identities']))
            store=FeedbackStore(LocalLibrary(root/'library'))
            render=store.add_render(audio,clip()['parameters'],'old-model','neural')
            feedback=dict(ratings=[rating(render,render_id=render['id'])],comparisons=[])
            (root/'index.html').write_text('<h1>comparison</h1>')
            result=feedback_comparison(feedback,store,root/'guided.npz',root,guided['feedback_training']['plan'])
            self.assertEqual(result['listeningCases'],1)
            self.assertTrue((root/'feedback-00-after.wav').is_file())
            self.assertIn('feedback.html',(root/'index.html').read_text())
