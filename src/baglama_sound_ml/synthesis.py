"""Nearest-sample baseline and pitch-controlled neural/DSP generation."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from .audio import RATE, finish, read_wav, validate_request
from .dataset import load_dataset
from .harmonics import HARMONICS, features
from .neural import load_model, predict


def sample(directory: Path, hz: float, course: str, duration: float,
           exclude_variant: str | None = None,
           allowed_identities: set[str] | None = None) -> tuple[np.ndarray, dict]:
    validate_request(hz, duration)
    rows = [r for r in load_dataset(directory) if r["course"] == course and r["variant"] != exclude_variant]
    if allowed_identities is not None:
        rows = [r for r in rows if r["identity"] in allowed_identities]
    if not rows:
        raise ValueError("No source recordings available for that course.")
    source = min(rows, key=lambda r: abs(np.log2(hz/r["frequency_hz"])))
    audio, rate = read_wav(directory/source["file"])
    if rate != RATE:
        raise ValueError("Dataset must use 48 kHz audio.")
    ratio = hz / source["frequency_hz"]
    positions = np.arange(round(duration*RATE))*ratio
    result = np.interp(positions, np.arange(len(audio)), audio, left=0, right=0)
    shift = float(1200*np.log2(ratio))
    return finish(result), dict(method="nearest-sample-varispeed", source_identity=source["identity"],
                                source_hz=source["frequency_hz"], shift_cents=shift,
                                warning="Large transposition; timbre may change substantially." if abs(shift)>400 else None,
                                duration_note="Varispeed changes decay time; missing tail is silence, not a loop.")


def neural(model: Path, hz: float, course: str, duration: float, seed: int = 7) -> tuple[np.ndarray, dict]:
    validate_request(hz, duration)
    weights, metadata = load_model(model)
    times = np.linspace(0, duration, max(16, round(duration*100)))
    controls = predict(weights, features(hz, times, course))
    samples = np.arange(round(duration*RATE))/RATE
    result = np.zeros(len(samples))
    rng = np.random.default_rng(seed)
    phases = rng.uniform(-np.pi, np.pi, HARMONICS)
    for index in range(HARMONICS):
        harmonic = (index+1)*hz
        if harmonic >= RATE*0.48:
            break
        envelope = np.interp(samples, times, controls[:, index])
        result += envelope*np.sin(2*np.pi*harmonic*samples + phases[index])
    # A simple stochastic attack residual, not a learned room/reverb model.
    noise = rng.standard_normal(len(samples))
    spectrum = np.fft.rfft(noise)
    frequencies = np.fft.rfftfreq(len(noise), 1/RATE)
    spectrum[(frequencies < 2000) | (frequencies > 9000)] = 0
    noise = np.fft.irfft(spectrum, n=len(noise))
    noise /= max(float(np.std(noise)), 1e-8)
    result += noise*np.interp(samples, times, controls[:, -1])*0.2
    # Training plucks are at most one second; extended output only decays.
    result *= np.exp(-4*np.maximum(samples-1, 0))
    low, high = metadata["frequency_ranges_hz"][course]
    return finish(result), dict(method="neural-harmonic-dsp", seed=seed,
                                warning="Pitch outside the training range; timbre is unvalidated extrapolation." if not low <= hz <= high else None,
                                training_range_hz=[low, high], model_parameters=metadata["parameters"],
                                duration_note="Timbre learned up to one second; longer tails use an exponential decay.")
