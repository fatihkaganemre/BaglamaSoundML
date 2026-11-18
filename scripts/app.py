#!/usr/bin/env python3
"""Makefile entry points; resolve the latest successful training run at launch."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def latest(root=ROOT):
    pointer = root / 'models/latest-training.json'
    if not pointer.exists():
        return None
    run = json.loads(pointer.read_text())
    if run.get('status') != 'complete':
        raise ValueError('Latest training run is incomplete. Run make train again.')
    for key, suffix in [('model', '.npz'), ('dataset', ''), ('library', ''), ('comparison', '.html')]:
        value = Path(run[key])
        if not value.is_absolute():
            value = root / value
        value = value.resolve()
        if root.resolve() not in value.parents or (suffix and value.suffix != suffix):
            raise ValueError('Latest training paths must stay inside this project.')
        run[key] = str(value)
    if not Path(run['model']).is_file() or not (Path(run['dataset']) / 'manifest.json').is_file():
        raise ValueError('Latest model or dataset is missing. Run make train again.')
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'restart', 'compare'])
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be from 1024 to 65535.')
    try:
        run = latest()
        if args.action == 'compare':
            if not run or not Path(run['comparison']).is_file():
                raise ValueError('No completed comparison found. Run make train first.')
            subprocess.run(['open', run['comparison']], check=True)
            return 0
        command = [str(ROOT / 'scripts/listen.sh'), '--port', str(args.port)]
        if run:
            for key in ['library', 'model', 'dataset']:
                command.extend(['--' + key, run[key]])
            print('Using training run: ' + run['run'], flush=True)
        else:
            print('No training run recorded; using the original model and dataset.', flush=True)
        if args.action == 'restart':
            from baglama_sound_ml.local_server import stop_server
            stop_server(ROOT, args.port)
            deadline = time.monotonic() + 10
            while True:
                try:
                    with socket.socket() as probe:
                        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        probe.bind(('127.0.0.1', args.port))
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ValueError('Port is still occupied. Retry make restart shortly or use PORT=8766.')
                    time.sleep(.1)
        os.chdir(ROOT)
        os.execv(command[0], command)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('Could not ' + args.action + ': ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
