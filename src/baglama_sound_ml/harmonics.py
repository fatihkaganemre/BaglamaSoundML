"""Pitch-conditioned harmonic features used by the experimental neural synthesizer."""
from __future__ import annotations
import numpy as np
from .audio import COURSES, RATE

HARMONICS = 24
FRAMES = 64


def features(hz: float, times: np.ndarray, course: str) -> np.ndarray:
    one_hot = np.zeros((len(times), len(COURSES)))
    one_hot[:, COURSES.index(course)] = 1
    return np.column_stack((np.minimum(times, 1), np.full(len(times), np.log2(hz / 196)), one_hot)).astype(np.float32)


def analyze(audio: np.ndarray, hz: float, frames: int = FRAMES) -> tuple[np.ndarray, np.ndarray]:
    """Project windowed frames onto source-pitch harmonics; estimate residual energy."""
    size = 4096
    times = np.linspace(0, len(audio)/RATE, frames, endpoint=False)
    centers = np.minimum((times*RATE).astype(int), len(audio)-1)
    padded = np.pad(audio, (size//2, size//2))
    windows = np.stack([padded[i:i+size] for i in centers])
    window = np.hanning(size)
    frequencies = hz * np.arange(1, HARMONICS+1)
    basis = np.exp(-2j*np.pi*np.outer(np.arange(size)/RATE, frequencies))
    amplitudes = 2*np.abs((windows*window) @ basis)/window.sum()
    amplitudes[:, frequencies >= RATE/2] = 0
    energy = np.mean(windows**2, axis=1)
    residual = np.sqrt(np.maximum(energy - np.sum(amplitudes**2, axis=1)/2, 0))
    values = np.column_stack((amplitudes, residual))
    return times, np.log(np.maximum(values, 1e-5)).astype(np.float32)


def spectral_distance(reference: np.ndarray, generated: np.ndarray) -> float:
    """Mean log-magnitude distance, normalized for overall recording gain."""
    size, hop = 2048, 512
    length = min(len(reference), len(generated))
    if length < size:
        raise ValueError("Audio is too short for spectral comparison.")
    window = np.hanning(size)
    spectra = []
    for audio in (reference[:length], generated[:length]):
        frames = np.lib.stride_tricks.sliding_window_view(audio, size)[::hop]
        magnitude = np.abs(np.fft.rfft(frames*window, axis=1))
        magnitude /= max(float(np.max(magnitude)), 1e-8)
        spectra.append(np.log(np.maximum(magnitude, 1e-4)))
    return float(np.mean(np.abs(spectra[0]-spectra[1])))
