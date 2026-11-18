#!/usr/bin/env python3
"""Versioned local library -> dataset -> model -> listening report workflow."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import json
import shlex
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from baglama_sound_ml.local_library import LocalLibrary
from baglama_sound_ml.dataset import import_packs
from baglama_sound_ml.neural import train
from baglama_sound_ml.report import compare
from baglama_sound_ml.feedback_store import FeedbackStore
from baglama_sound_ml.feedback_training import feedback_comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, default=600)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--holdout-variant', default='karar-G-sharp')
    parser.add_argument('--library', type=Path, default=ROOT / 'data/library')
    parser.add_argument('--no-feedback', action='store_true', help='Train real-only control run; still save feedback and listening comparisons.')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.steps < 1 or not 0 <= args.seed < 2**32 or not 1024 <= args.port <= 65535:
        parser.error('Use positive steps, a seed from 0 to 4294967295, and a port from 1024 to 65535.')
    library = args.library.resolve()
    if not (library / 'library.sqlite3').is_file():
        parser.error('Library not found. Import your Baglamator ZIPs in the app first.')
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    source = ROOT / 'data' / ('import-' + tag)
    dataset = ROOT / 'data' / ('recordings-' + tag)
    model = ROOT / 'models' / ('baglama-' + tag + '.npz')
    output = ROOT / 'outputs' / ('comparison-' + tag)
    output.mkdir(parents=True, exist_ok=False)
    record = dict(run=tag, status='running', library=str(library), dataset=str(dataset), model=str(model), comparison=str(output / 'index.html'), steps=args.steps, seed=args.seed, holdoutVariant=args.holdout_variant,
                  caveat='Validation selects the checkpoint; it is not an independent final test. Listening is required to judge sound quality.')
    def save_record():
        (output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
    save_record()
    try:
        print('1/4 Exporting active library samples with saved trims…', flush=True)
        local=LocalLibrary(library)
        store=FeedbackStore(local)
        feedback=store.report()
        feedback['comparisonRenders']={}
        for pair in feedback['comparisons']:
            for key in ['a_id','b_id']:
                feedback['comparisonRenders'][pair[key]]=store.render(pair[key])
        (output/'feedback-snapshot.json').write_text(json.dumps(feedback,indent=2)+'\n')
        archive = local.export_real()
        source.mkdir(parents=True, exist_ok=False)
        (source / 'library.zip').write_bytes(archive)
        print('2/4 Preparing and deduplicating recordings…', flush=True)
        imported = import_packs(source, dataset)
        record.update(eligible=imported['imported_count'], skipped=imported['skipped'])
        print(f"  Eligible: {record['eligible']}; excluded: {json.dumps(record['skipped'])}", flush=True)
        print('3/4 Training a separate model…', flush=True)
        trained = train(dataset, model, args.steps, args.holdout_variant, args.seed, feedback=None if args.no_feedback else feedback)
        plan=trained['feedback_training']['plan']
        print(f"  Feedback: {len(plan['focuses'])} applied focus signals; {trained['feedback_training']['weighted_frames']} real frames weighted.",flush=True)
        record.update(training=trained['training_count'], validation=trained['validation_count'], validationMSE=trained['best_validation_normalized_mse'])
        print(f"  Training: {record['training']}; validation: {record['validation']}", flush=True)
        print('4/4 Building reference / sample / ML listening comparison…', flush=True)
        result = compare(dataset, model, output)
        feedback_result=feedback_comparison(feedback,store,model,output,plan)
        record.update(status='complete', comparisonExamples=result['recordings'], feedback=feedback_result, feedbackEnabled=not args.no_feedback)
        (output/'feedback-plan.json').write_text(json.dumps(trained['feedback_training'],indent=2)+'\n')
        save_record()
        pointer = ROOT / 'models/latest-training.json'
        temporary = pointer.with_suffix('.' + tag + '.tmp')
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(pointer)
    except Exception as error:
        record.update(status='failed', error=str(error)); save_record()
        print(f'Run failed: {error}\nPrevious models and latest successful run are preserved.\nDetails: {output / "run.json"}', file=sys.stderr)
        return 1
    command = [str(ROOT / 'scripts/listen.sh'), '--port', str(args.port), '--library', str(library), '--model', str(model), '--dataset', str(dataset)]
    print('\nFinished. Listen before deciding whether this model is better.')
    print('Comparison: ' + str(output / 'index.html'))
    print('Start this model: ' + shlex.join(command))
    print(f'If the app is already running, stop it first: ./scripts/listen.sh --stop --port {args.port}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
