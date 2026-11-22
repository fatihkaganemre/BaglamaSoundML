import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
from baglama_sound_ml.audio import RATE, pitch, read_wav, write_wav
from baglama_sound_ml.continuation import compare_continuations
from baglama_sound_ml.dataset import import_packs
from baglama_sound_ml.synthesis import sample, neural


class PipelineTests(unittest.TestCase):
    def test_midpoint_prediction_does_not_use_the_hidden_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            time = np.arange(RATE) / RATE
            note = 0.5 * np.cos(2 * np.pi * 110 * time) * np.exp(-3 * time)
            midpoint = RATE // 2
            write_wav(root / "first.wav", note)
            write_wav(root / "second.wav", np.concatenate((note[:midpoint], -0.2 * note[midpoint:])))
            rows = [dict(identity=name, file=f"{name}.wav", course="ust", frequency_hz=220)
                    for name in ("first", "second")]
            (root / "manifest.json").write_text(json.dumps(dict(recordings=rows)))
            model = root / "fixture.npz"
            weights = {"mean": np.zeros(25), "scale": np.ones(25)}
            for layer, inputs, outputs in ((0, 5, 48), (2, 48, 48), (4, 48, 25)):
                weights[f"{layer}.weight"] = np.zeros((outputs, inputs))
                weights[f"{layer}.bias"] = np.zeros(outputs)
            metadata = dict(schema_version=1, training_identities=["training"],
                            validation_identities=["first", "second"], holdout_variant="held")
            np.savez(model, **weights, metadata=np.array(json.dumps(metadata)))

            output = root / "report"
            first, second = compare_continuations(root, model, output)["results"]
            self.assertEqual(first["cut_samples"], midpoint)
            self.assertAlmostEqual(first["prefix_pitch_hz"], 110, delta=0.1)
            for method in ("prefix-decay", "neural-envelope"):
                audio, _ = read_wav(output / first["clips"][method])
                other, _ = read_wav(output / second["clips"][method])
                prefix, _ = read_wav(output / first["clips"]["prefix"])
                self.assertEqual(len(audio), RATE)
                np.testing.assert_array_equal(audio, other)
                np.testing.assert_array_equal(audio[:midpoint], prefix)
                self.assertNotEqual(first["methods"][method], second["methods"][method])

    def test_import_deduplicates_waveforms_and_excludes_uncertain_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = (0.1*np.sin(2*np.pi*110*np.arange(RATE)/RATE)).astype('<f4').tobytes()
            for index, quality in enumerate(('consistent', 'consistent', 'uncertain')):
                metadata = dict(audioFormat='pcm_f32le_mono', sampleRate=RATE,
                                label=dict(instrumentID='kisaSap', tuningID='baglama', variantID='karar-A',
                                           stringID='kisaSap.baglama.ust.1', target=dict(note=9)),
                                pitchAnalysis=dict(quality=quality, estimatedFrequencyHertz=110))
                with zipfile.ZipFile(root/f'{index}.zip','w') as archive:
                    archive.writestr(f'Samples/{index}.json',json.dumps(metadata))
                    archive.writestr(f'Samples/{index}.f32',raw)
            result = import_packs(root,root/'prepared')
            self.assertEqual(result['imported_count'],1)
            self.assertEqual(result['skipped']['duplicate_waveform'],1)
            self.assertEqual(result['skipped']['uncertain_or_missing_pitch'],1)
            self.assertNotIn('recordedAt',json.dumps(result))

    def test_baseline_does_not_use_heldout_recording_or_clamp_low_pitch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            time=np.arange(RATE)/RATE
            write_wav(root/'training.wav',0.5*np.sin(2*np.pi*220*time))
            write_wav(root/'validation.wav',0.5*np.sin(2*np.pi*55*time))
            rows=[dict(identity='training', file='training.wav', course='ust', variant='train', frequency_hz=220),
                  dict(identity='validation', file='validation.wav', course='ust', variant='holdout', frequency_hz=55)]
            (root/'manifest.json').write_text(json.dumps(dict(recordings=rows)))
            result, details=sample(root,55,'ust',0.5,allowed_identities={'training'})
            self.assertEqual(details['source_identity'],'training')
            self.assertAlmostEqual(details['shift_cents'],-2400)
            self.assertLess(abs(pitch(result[int(RATE*.03):])-55),0.1)

    def test_neural_renderer_controls_frequency_and_is_seed_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            model=Path(directory)/'fixture.npz'
            mean=np.full(25,-14,dtype=np.float32)
            mean[0]=-1
            weights={'0.weight':np.zeros((48,5)),'0.bias':np.zeros(48),
                     '2.weight':np.zeros((48,48)),'2.bias':np.zeros(48),
                     '4.weight':np.zeros((25,48)),'4.bias':np.zeros(25),
                     'mean':mean,'scale':np.ones(25),
                     'metadata':np.array(json.dumps(dict(schema_version=1, frequency_ranges_hz={'ust':[80,200]}, parameters=0)))}
            np.savez(model,**weights)
            result,details=neural(model,110,'ust',0.5,seed=42)
            again,_=neural(model,110,'ust',0.5,seed=42)
            self.assertTrue(np.array_equal(result,again))
            self.assertLess(abs(pitch(result[int(RATE*.03):])-110),0.1)
            self.assertIsNone(details['warning'])
