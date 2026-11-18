import tempfile
import unittest
from pathlib import Path
import numpy as np
from baglama_sound_ml.audio import RATE, frequency, finish, pitch, read_wav, write_wav, validate_request
from baglama_sound_ml.harmonics import features


class AudioTests(unittest.TestCase):
    def test_explicit_octave_and_enharmonics(self):
        self.assertAlmostEqual(frequency("A2"), 110)
        self.assertAlmostEqual(frequency("G#2"), frequency("Ab2"))
        self.assertAlmostEqual(frequency("A4", 442), 442)
        self.assertAlmostEqual(frequency("B#3"), frequency("C4"))
        with self.assertRaises(ValueError):
            frequency("G")

    def test_period_measurement_rejects_silence_and_recovers_low_note(self):
        time = np.arange(RATE//2)/RATE
        signal = np.sin(2*np.pi*103.826*time)+0.4*np.sin(2*np.pi*207.652*time)
        original = signal.copy()
        self.assertLess(abs(pitch(signal)-103.826), 0.1)
        self.assertTrue(np.array_equal(signal, original))
        self.assertIsNone(pitch(np.zeros(len(signal))))

    def test_export_headroom_and_roundtrip(self):
        time = np.arange(RATE//2)/RATE
        signal = finish(4*np.sin(2*np.pi*440*time))
        self.assertLessEqual(np.max(np.abs(signal)), 0.800001)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"note.wav"
            write_wav(path, signal)
            actual, rate = read_wav(path)
        self.assertEqual(rate, RATE)
        self.assertLess(np.max(np.abs(signal-actual)), 5e-5)
        self.assertAlmostEqual(float(actual[0]), 0)
        self.assertAlmostEqual(float(actual[-1]), 0)

    def test_invalid_requests_fail_before_allocating_audio(self):
        for hz, seconds in ((float("nan"),1),(float("inf"),1),(20,1),(440,0),(440,100)):
            with self.assertRaises(ValueError):
                validate_request(hz, seconds)
        with self.assertRaises(ValueError):
            finish(np.zeros(100))

    def test_pitch_and_course_are_distinct_controls(self):
        times = np.linspace(0,1,10)
        upper = features(110,times,"ust")
        middle = features(110,times,"orta")
        self.assertFalse(np.array_equal(upper,middle))
        self.assertEqual(upper.shape,(10,5))
