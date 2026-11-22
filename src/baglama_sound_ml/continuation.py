"""Offline midpoint continuation using prefix-fitted oscillators."""
from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np

from .audio import RATE, pitch, read_wav, validate_request, write_wav
from .dataset import load_dataset
from .harmonics import HARMONICS, envelope_distance, features, spectral_distance
from .neural import load_model, predict


def estimate_prefix_pitch(prefix: np.ndarray) -> float:
    estimates = [
        pitch(prefix[start:start + 6144])
        for start in range(RATE // 50, len(prefix) - 2047, 3072)
    ]
    estimates = [hz for hz in estimates if hz is not None and 40 <= hz <= 2000]
    if not estimates:
        raise ValueError("No reliable pitch estimate in the recorded first half.")
    return float(np.median(estimates))


def predict_tails(prefix: np.ndarray, count: int, hz: float, course: str,
                  weights: dict) -> dict[str, np.ndarray]:
    """Fit levels and phases on the prefix, then extrapolate two sets of envelopes."""
    validate_request(hz, (len(prefix) + count) / RATE)
    frequencies = hz * np.arange(1, HARMONICS + 1)
    frequencies = frequencies[frequencies < 0.48 * RATE]
    window_size = min(round(0.08 * RATE), len(prefix) // 3)
    window = np.hanning(window_size)
    offsets = (np.arange(window_size) - (window_size - 1) / 2) / RATE
    basis = np.exp(-2j * np.pi * np.outer(offsets, frequencies))
    gain = max(float(np.max(np.abs(prefix))), 1e-8)
    frames = prefix[-3 * window_size:].reshape(3, window_size) / gain
    partials = 2 * ((frames * window) @ basis) / window.sum()
    levels = np.log(np.maximum(np.abs(partials), 1e-6))

    center = len(prefix) - (window_size + 1) / 2
    times = np.arange(len(prefix), len(prefix) + count) / RATE
    elapsed = times - center / RATE
    phase = np.angle(partials[-1]) + 2 * np.pi * np.outer(elapsed, frequencies)
    oscillators = np.cos(phase)

    # Cap extrapolated slopes to keep beating and noise in a short fit from
    # turning into sustained positive gain.
    slope = np.clip((levels[-1] - levels[0]) / (2 * window_size / RATE), -60, 0)
    decay = levels[-1] + np.outer(elapsed, slope)
    anchor = levels[-1] + (len(prefix) / RATE - center / RATE) * slope

    # Use the trained MLP's relative changes. The observed prefix determines
    # the absolute level and phase, so the model can continue this take.
    controls = predict(weights, features(hz, times, course))[:, :len(frequencies)]
    neural = anchor + np.log(controls / controls[0])
    tails = {}
    for name, log_levels in (("prefix-decay", decay), ("neural-envelope", neural)):
        tail = gain * np.sum(np.exp(np.minimum(log_levels, 0)) * oscillators, axis=1)
        # Smooth the splice using only the last recorded sample.
        fade = min(len(tail), RATE // 200)
        tail[:fade] += (prefix[-1] - tail[0]) * np.linspace(1, 0, fade)
        tails[name] = np.clip(tail, -1, 1)
    return tails


def compare_continuations(directory: Path, model: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("Choose a new continuation output directory.")
    weights, metadata = load_model(model)
    training = set(metadata["training_identities"])
    validation = set(metadata["validation_identities"])
    if training & validation:
        raise ValueError("Model contains overlapping training and validation identities.")
    rows = [row for row in load_dataset(directory) if row["identity"] in validation]
    if {row["identity"] for row in rows} != validation or not rows:
        raise ValueError("Use the dataset paired with this model's validation recordings.")

    output.mkdir(parents=True, exist_ok=False)
    results, skipped, sections = [], [], []
    for index, row in enumerate(rows):
        reference, rate = read_wav(directory / row["file"])
        if rate != RATE:
            raise ValueError("Continuation requires prepared 48 kHz recordings.")
        cut = len(reference) // 2
        prefix = reference[:cut]
        try:
            hz = estimate_prefix_pitch(prefix)
        except ValueError as error:
            skipped.append(dict(identity=row["identity"], reason=str(error)))
            continue

        tails = predict_tails(prefix, len(reference) - cut, hz, row["course"], weights)
        actual_tail = reference[cut:]
        entry = dict(identity=row["identity"], course=row["course"], cut_samples=cut,
                     prefix_pitch_hz=hz, clips={}, methods={})
        players = []
        clips = {"prefix": prefix, "reference": reference}
        clips.update({name: np.concatenate((prefix, tail)) for name, tail in tails.items()})
        for name, audio in clips.items():
            filename = f"{index:02d}-{name}.wav"
            write_wav(output / filename, audio)
            entry["clips"][name] = filename
            label = {"prefix": "Model input", "reference": "Actual continuation",
                     "prefix-decay": "Extrapolated decay", "neural-envelope": "Neural continuation"}[name]
            if name in tails:
                tail = tails[name]
                envelope_error = envelope_distance(actual_tail, tail)
                reference_rms = np.sqrt(np.mean(actual_tail**2))
                generated_rms = np.sqrt(np.mean(tail**2))
                level_error = float(20 * np.log10(max(generated_rms, 1e-8) / max(reference_rms, 1e-8)))
                entry["methods"][name] = dict(rms_envelope_distance_db=envelope_error,
                                               rms_level_error_db=level_error,
                                               log_spectral_distance=spectral_distance(actual_tail, tail))
                label += f" · envelope error {envelope_error:.1f} dB · level difference {level_error:+.1f} dB"
            players.append(f'<p>{label}<br><audio controls preload="none" src="{filename}"></audio></p>')
        sections.append(f'<section><h2>{html.escape(row["course"])} · {hz:.2f} Hz · '
                        f'cut at {cut / RATE:.3f} s</h2>{"".join(players)}</section>')
        results.append(entry)

    report = dict(model=str(model), dataset=str(directory), recordings=len(results),
                  validation_variant=metadata["holdout_variant"], skipped=skipped, results=results)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "index.html").write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bağlama midpoint continuation</title>
<style>body{font:17px system-ui;max-width:850px;margin:40px auto;padding:0 24px}
section{border-bottom:1px solid #aaa;padding:12px 0}audio{width:min(100%,420px)}</style>
<h1>Bağlama midpoint continuation</h1>
<p>Each recording was split at its midpoint. Playback starts with the same recorded
first half. The rest is either the actual recording, an extrapolation of the observed
harmonic decay, or a prediction shaped by the trained neural envelopes.</p>
<p>Scores cover the second half only. Envelope error compares peak-relative 10 ms RMS
levels. The signed level difference compares overall RMS. These examples were held
out during training and used for checkpoint selection.</p>
''' + f"<p>{len(results)} examples · {len(skipped)} skipped</p>\n" + "\n".join(sections) + "</html>\n")
    return report
