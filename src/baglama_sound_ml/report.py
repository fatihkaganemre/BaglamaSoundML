"""Generate a local side-by-side listening report using an entirely held-out variant."""
from __future__ import annotations
from pathlib import Path
import html
import json
import shutil
import numpy as np
from .audio import RATE, pitch, read_wav, write_wav
from .dataset import load_dataset
from .harmonics import envelope_distance, spectral_distance
from .neural import load_model
from .synthesis import sample, neural


def compare(directory: Path, model: Path, output: Path) -> dict:
    if (output/"report.json").exists():
        raise ValueError("Report already exists; choose a new output directory.")
    _, metadata = load_model(model)
    allowed = set(metadata["training_identities"])
    validation = set(metadata["validation_identities"])
    if allowed & validation:
        raise ValueError("Model contains overlapping training and validation identities.")
    rows = [r for r in load_dataset(directory) if r["identity"] in validation]
    if not rows:
        raise ValueError("Dataset does not contain the model's validation recordings.")
    output.mkdir(parents=True, exist_ok=True)
    results, cards = [], []
    for index, row in enumerate(rows):
        reference, rate = read_wav(directory/row["file"])
        if rate != RATE:
            raise ValueError("Reference audio must use 48 kHz.")
        hz, duration = row["frequency_hz"], len(reference)/RATE
        reference_name = f"{index:02d}-reference.wav"
        shutil.copyfile(directory/row["file"], output/reference_name)
        entry = dict(identity=row["identity"], course=row["course"], requested_hz=hz,
                     reference=reference_name, methods={})
        players = [f'<p>Recorded reference<br><audio controls preload="none" src="{reference_name}"></audio></p>']
        for method in ("sample", "neural"):
            if method == "sample":
                generated, details = sample(directory, hz, row["course"], duration,
                                             allowed_identities=allowed)
                assert details["source_identity"] not in validation
            else:
                generated, details = neural(model, hz, row["course"], duration)
            filename = f"{index:02d}-{method}.wav"
            write_wav(output/filename, generated)
            estimates = [pitch(generated[int(RATE*t):]) for t in (0.08, 0.18, 0.28)]
            estimates = [value for value in estimates if value is not None]
            error = float(np.median([1200*np.log2(value/hz) for value in estimates])) if estimates else None
            details.update(file=filename, estimated_pitch_error_cents=error,
                           rms_envelope_distance_db=envelope_distance(reference, generated),
                           log_spectral_distance=spectral_distance(reference, generated))
            entry["methods"][method] = details
            error_text = f"{error:+.2f} cents" if error is not None else "period ambiguous"
            envelope_error = details["rms_envelope_distance_db"]
            players.append(f'<p>{method} · {error_text} · envelope error {envelope_error:.1f} dB<br>'
                           f'<audio controls preload="none" src="{filename}"></audio></p>')
        results.append(entry)
        cards.append(f'<section><h2>{html.escape(row["course"])} · {hz:.2f} Hz</h2>{"".join(players)}</section>')
    summary = dict(validation_variant=metadata["holdout_variant"], recordings=len(rows),
                   caveat="Validation also selected the checkpoint. Pitch checks and spectral distance do not prove perceptual realism; listen to the examples.",
                   results=results)
    (output/"report.json").write_text(json.dumps(summary, indent=2)+"\n")
    (output/"index.html").write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BaglamaSoundML comparison</title>
<style>body{font:17px system-ui;max-width:1000px;margin:40px auto;padding:0 24px;background:#102324;color:#eee}section{border:1px solid #607274;border-radius:14px;padding:20px;margin:20px 0}audio{width:min(100%,400px)}h1,h2{color:#edce86}</style>
<h1>BaglamaSoundML · held-out listening comparison</h1>
<p>Reference: held-out recording. Sample: nearest training recording, transposed. Neural: learned harmonic envelopes with DSP-controlled pitch.</p>
<p>This tiny dataset is an experiment. Validation selected the model checkpoint; this is not an independent test set. Spectral distance is not a listening-quality score.</p>
<p>Envelope error compares 10 ms RMS levels relative to each clip’s loudest frame. Lower values indicate closer amplitude contours.</p>
''' + "\n".join(cards) + "</html>\n")
    return summary
