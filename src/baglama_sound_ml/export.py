"""Portable inference export with no recording IDs or training-data paths."""
from pathlib import Path
import json
from importlib.resources import files
from .neural import load_model


def portable_model(path: Path) -> dict:
    weights, metadata = load_model(path)
    return dict(schemaVersion=1,
                layers=[dict(weights=weights[f'{layer}.weight'].tolist(), biases=weights[f'{layer}.bias'].tolist()) for layer in (0,2,4)],
                mean=weights['mean'].tolist(), scale=weights['scale'].tolist(),
                frequencyRangesHz=metadata['frequency_ranges_hz'])


def export_swift(model: Path, output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(portable_model(model), separators=(',', ':'), allow_nan=False)+'\n')
    return dict(output=str(output), bytes=output.stat().st_size, format='BaglamaSoundML portable JSON v1')


def playground(model: Path, output: Path) -> dict:
    template = files('baglama_sound_ml').joinpath('resources/playground.html').read_text()
    payload = json.dumps(portable_model(model), separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace('__BAGLAMA_MODEL__', payload))
    return dict(output=str(output), standalone=True, note='All synthesis runs locally in this page; no audio files or server API are fetched.')
