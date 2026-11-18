"""Validated owner-entered instrument/string observations; unknown values remain null."""
import math
from .capture_catalog import catalog


def validate_string_labels(body,expected):
    if not any(key in body for key in ('instrumentID','tuningID','strings')):
        return {}  # Legacy cases never acquired these labels; do not invent them.
    try:
        instrument=next(i for i in catalog()['instruments'] if i['id']==body.get('instrumentID'))
        tuning=next(t for t in instrument['tunings'] if t['id']==body.get('tuningID'))
        variant=next(v for v in tuning['variants'] if v['kararPitchClass']==expected)
    except StopIteration as error:
        raise ValueError('Choose a baglama type and catalog tuning arrangement.') from error
    targets=[(c['id'],s) for c in variant['courses'] for s in c['strings']]
    values=body.get('strings')
    if not isinstance(values,list) or len(values)!=len(targets):
        raise ValueError('Provide one row for each catalog string, in top-to-bottom order; unknown values may be blank.')
    labels=[]
    for index,((course,target),value) in enumerate(zip(targets,values)):
        if not isinstance(value,dict) or value.get('stringID')!=target['id']:
            raise ValueError('String identity/order does not match the selected instrument and tuning.')
        note=value.get('note');octave=value.get('octave');cents=value.get('cents')
        if note is not None and (type(note) is not int or not 0<=note<=11):raise ValueError('String note must be a pitch class from 0 to 11, or unknown.')
        if octave is not None and (type(octave) is not int or not 0<=octave<=7):raise ValueError('String octave must be 0–7, or unknown.')
        if cents is not None and (type(cents) not in (int,float) or not math.isfinite(cents) or not -1200<=cents<=1200):raise ValueError('String cents must be finite, from -1200 to +1200, or unknown.')
        if note is None and (octave is not None or cents is not None):raise ValueError('Choose a string note before entering its octave or cents offset.')
        labels.append(dict(stringID=target['id'],position=index+1,course=course,note=note,octave=octave,cents=cents))
    return dict(instrumentID=instrument['id'],tuningID=tuning['id'],strings=labels)
