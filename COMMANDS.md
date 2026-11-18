# Everyday commands

From the project directory, run `make` or `make help`. `make --help` shows Make's own help instead.

| Command | Action |
| --- | --- |
| `make start` | Start the local app with the latest successful model, or default paths. |
| `make stop` | Stop this project's server on the selected port. |
| `make restart` | Restart with the latest successful model and matching dataset. |
| `make train` | Export real samples, prepare a dataset, train and build comparisons. |
| `make compare` | Open the latest successful listening comparison on macOS. |
| `make evaluate-final-tone` | Score saved final-tone evaluation cases without training. |
| `make test` | Run Python regression tests. |

Open http://127.0.0.1:8765/ after starting. Keep the Terminal open; Ctrl+C stops the app. No model is distributed: a fresh checkout can use final-tone detection and the library, but must supply/train a model before neural generation.

## Setup

```sh
python3 -m venv .venv
.venv/bin/python3 -m pip install -e .
# Optional, for training:
.venv/bin/python3 -m pip install -e '.[train]'
```

Launchers explicitly use `.venv/bin/python3`. Python/NumPy/PyTorch belong to the research environment, not the Swift runtime.

## Workflow

1. `make start`; import compatible real-recording ZIPs and review samples.
2. `make train` in another Terminal. Avoid editing the library during its export step.
3. `make compare` to listen. Training success is not proof of perceptual improvement.
4. `make restart`, then refresh the browser, to use the latest successful model.

For final-tone examples, detect a real strum, enter the independently known instrument/final-tone/string labels, and explicitly save the case. `make evaluate-final-tone` reruns detection on active cases. Cases that influence detector development are not independent final-test data.

## Options

```sh
make train STEPS=1200 SEED=7
make train FEEDBACK=0
make start PORT=8766
make restart PORT=8766
make stop PORT=8766
```

Use the same `PORT` for start/stop/restart. Training versions are separate and the running app is not switched automatically. `models/latest-training.json` points to the latest successful run; failed runs do not replace it.

Advanced help:

```sh
./scripts/listen.sh --help
./scripts/retrain.sh --help
.venv/bin/python3 -m baglama_sound_ml --help
.venv/bin/python3 scripts/evaluate-final-tone.py --help
```

## Local data

Back up `data/library/` while the server is stopped, including the final-tone test-case subdirectory. Library Trash is recoverable. Synthesis exports and strum evaluation exports are separate. Recordings, feedback, trained weights and generated outputs are Git-ignored and are not part of the public checkout or Swift package.
