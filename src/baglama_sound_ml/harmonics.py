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
    # Keep at least three fundamental cycles where possible without averaging
    # higher notes across most of their attack.
    size = int(np.clip(2 * np.ceil(1.5 * RATE / hz), 1024, 4096))
    duration = len(audio) / RATE
    times = np.linspace(0, duration, frames, endpoint=False)
    attack_times = np.arange(0, min(duration, 0.05), 0.005)
    times = np.unique(np.round(np.concatenate((times, attack_times)) * RATE)) / RATE
    centers = np.minimum((times*RATE).astype(int), len(audio)-1)
    padded = np.pad(audio, (size//2, size//2))
    windows = np.stack([padded[i:i+size] for i in centers])
    window = np.hanning(size)
    frequencies = hz * np.arange(1, HARMONICS+1)
    basis = np.exp(-2j*np.pi*np.outer(np.arange(size)/RATE, frequencies))
    amplitudes = 2*np.abs((windows*window) @ basis)/window.sum()
    amplitudes[:, frequencies >= RATE/2] = 0
    energy = (windows**2 @ window) / window.sum()
    residual = np.sqrt(np.maximum(energy - np.sum(amplitudes**2, axis=1)/2, 0))
    values = np.column_stack((amplitudes, residual))
    return times, np.log(np.maximum(values, 1e-5)).astype(np.float32)


def envelope_distance(reference: np.ndarray, generated: np.ndarray) -> float:
    """Mean absolute difference of peak-relative 10 ms RMS levels in dB."""
    block_size = RATE // 100
    blocks = min(len(reference), len(generated)) // block_size
    if not blocks:
        raise ValueError("Audio is too short for envelope comparison.")
    levels = []
    for audio in (reference, generated):
        frames = audio[:blocks * block_size].reshape(blocks, block_size)
        rms = np.sqrt(np.mean(frames**2, axis=1))
        levels.append(20 * np.log10(np.maximum(rms / max(rms.max(), 1e-8), 1e-3)))
    return float(np.mean(np.abs(levels[0] - levels[1])))


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
