"""Offline checks; the selected target never drives the measured pitch estimate."""
from __future__ import annotations
import numpy as np
from .audio import pitch


def analyze_capture(audio: np.ndarray, rate: int) -> dict:
    centered = audio.astype(np.float64) - float(np.mean(audio))
    peak = float(np.max(np.abs(centered)))
    rms = float(np.sqrt(np.mean(centered**2)))
    warnings = []
    if np.mean(np.abs(audio) >= 0.98) > 0.001:
        warnings.append('Clipping detected; reduce input gain and retry.')
    if rms < 0.002:
        warnings.append('Quiet recording; move closer or reduce room noise.')
    estimates = []
    if peak > 1e-5:
        start = int(np.flatnonzero(np.abs(centered) >= peak*0.1)[0]) + int(rate*0.04)
        size = min(6144, len(audio)-start)
        if size >= 2048:
            starts = np.unique(np.linspace(start, max(start, len(audio)-size), 9).astype(int))
            for offset in starts:
                block = centered[offset:offset+size]
                if np.sqrt(np.mean(block**2)) < max(1e-5, peak*0.005):
                    continue
                hz = pitch(block, rate)
                if hz is not None:
                    estimates.append(hz)
    measured = sorted(estimates)[len(estimates)//2] if estimates else None
    spread = float(np.percentile(np.abs(1200*np.log2(np.array(estimates)/measured)),90)) if estimates else None
    quality = 'consistent' if len(estimates)>=3 and spread <= 15 else 'uncertain' if estimates else 'insufficientData'
    if quality != 'consistent':
        warnings.append('Pitch is uncertain. Keep this take for review or retry; it is not confirmed training data.')
    return dict(algorithm='YIN-style multi-window check', quality=quality,
                estimatedFrequencyHertz=measured, temporalSpreadCents=spread,
                voicedWindowCount=len(estimates), peak=peak, rms=rms, warnings=warnings)
