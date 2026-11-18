"""Verified capture labels from Baglamator's existing tuning catalog."""
from __future__ import annotations
import json
import math
from importlib.resources import files


def catalog() -> dict:
    return json.loads(files('baglama_sound_ml').joinpath('resources/capture-catalog.json').read_text())


def validate_label(value: dict) -> dict:
    try:
        instrument = next(i for i in catalog()['instruments'] if i['id'] == value['instrumentID'])
        tuning = next(t for t in instrument['tunings'] if t['id'] == value['tuningID'])
        variant = next(v for v in tuning['variants'] if v['id'] == value['variantID'])
        strings = [s for c in variant['courses'] for s in c['strings']]
        target = next(s for s in strings if s['id'] == value['stringID'])
    except (StopIteration, KeyError, TypeError) as error:
        raise ValueError('Choose an instrument, tuning, final tone and physical string from the catalog.') from error
    reference = float(value.get('referenceHertz', 440))
    if not math.isfinite(reference) or not 400 <= reference <= 480:
        raise ValueError('A4 reference must be between 400 and 480 Hz.')
    target = dict(target)
    if value.get('octave') not in (None, ''):
        octave = int(value['octave'])
        if not 0 <= octave <= 7 or ('octave' in target and octave != target['octave']):
            raise ValueError('Use the verified octave shown for this physical string.')
        target['octave'] = octave
    truth = value.get('groundTruthHertz')
    truth_source = str(value.get('groundTruthSource', '')).strip()[:200]
    if truth not in (None, ''):
        truth = float(truth)
        if not math.isfinite(truth) or not 20 <= truth <= 5000 or not truth_source:
            raise ValueError('A ground-truth frequency needs a value from 20–5000 Hz and its measurement source.')
    elif truth_source:
        raise ValueError('Enter the measured ground-truth frequency or clear its source.')
    else:
        truth = None
    return dict(instrumentID=instrument['id'], tuningID=tuning['id'], variantID=variant['id'],
                stringID=target['id'], physicalStringNumber=strings.index(next(s for s in strings if s['id']==target['id']))+1,
                target=target, referencePitch=dict(a4Hertz=reference),
                measuredGroundTruthHertz=truth, measuredGroundTruthSource=truth_source or None)
