#!/usr/bin/env python3
"""Evaluate the current final-tone detector against explicitly saved owner labels."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from baglama_sound_ml.final_tone_cases import FinalToneCases

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=Path,default=ROOT/'data/library/final-tone-tests')
    args=parser.parse_args()
    if not (args.cases/'cases.sqlite3').is_file():
        print('No saved final-tone test cases yet. Label and save a real strum in the detector.');return 0
    report=FinalToneCases(args.cases).evaluate()
    output=ROOT/'outputs'/('final-tone-evaluation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);output.mkdir(parents=True,exist_ok=False)
    path=output/'report.json';path.write_text(json.dumps(report,indent=2)+'\n')
    print(f"Evaluated: {report['total']}; unsupported setup: {report['unsupportedCount']}; correct: {report['correct']}; incorrect: {report['detected']-report['correct']}; abstained: {report['abstained']}")
    print('Accuracy including abstentions: '+(f"{report['accuracyIncludingAbstentions']:.1%}" if report['total'] else 'not available (no supported active cases)'))
    print('Report: '+str(path));print(report['caveat']);return 0

if __name__=='__main__':raise SystemExit(main())
