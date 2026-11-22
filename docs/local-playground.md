# Local playground and training

## Install the local playground

Requirements: Python 3.9+ (3.11+ recommended), Git, and a browser supporting Web Audio. The convenience Makefile and comparison opener target macOS. PyTorch is required only for model training, not detection or inference.

```sh
git clone https://github.com/fatihkaganemre/BaglamaSoundML.git
cd BaglamaSoundML
python3 -m venv .venv
.venv/bin/python3 -m pip install -e .
make start
```

Open **http://127.0.0.1:8765/**. For training support:

```sh
.venv/bin/python3 -m pip install -e '.[train]'
```

The scripts explicitly use `.venv/bin/python3`, avoiding differences between Terminal Python environments. No model is downloaded automatically. On a fresh checkout, generation stays unavailable until you provide a model; detection and local data review remain usable.

### Detect a final tone

1. Open **Final tone detector** and set the A4 reference.
2. Accept the local microphone explanation and click **Start detection**.
3. Allow microphone access. Strum all open courses top to bottom when “Microphone on” appears, then let them ring.
4. After up to five seconds, the microphone stops and the clip is analyzed. Alternatively choose a 0.4–8 second WAV.

The result reports **Final tone** when the course pattern is clear and the resolved pitches meet its tuning-consistency threshold; **Possible final tone** when the pattern is recognizable but needs tuning; or **strum again** when evidence is insufficient. Course notes, frequencies and cents are shown. The evidence score is heuristic, not a calibrated probability.

This prototype does not verify stroke order or every physical string, and it does not recognize makam. Use a clear solo open-string strum, without a metronome or accompaniment. The synthetic example exercises the controls; it is not evidence of real-instrument accuracy.

### Save evaluation examples

After a real analysis, enter **Baglama type**, **Tuning arrangement**, **Known final tone**, and any independently known per-string notes, octaves and signed cents. Unknowns stay blank; `0` explicitly means zero cents. Nothing is filled from the detector guess.

Explicitly choose **Save / update test case** to retain audio and annotations locally. Replay, revise, export, and recoverably trash cases from the saved-case section.

```sh
make evaluate-final-tone
```

This evaluates the current detector against saved labels and writes a local report. Unsupported setups are reported separately. These cases are separate from synthesis training. If cases guide algorithm development, they are development evaluation data, not an independent final test set.

## Call functions from Python

### Get a final tone

```python
from pathlib import Path
from baglama_sound_ml.audio import read_wav
from baglama_sound_ml.final_tone import detect_final_tone

# This helper accepts mono 16-bit PCM WAV.
samples, sample_rate = read_wav(Path("strum.wav"))
result = detect_final_tone(samples, sample_rate, reference=440.0)

if result["finalTone"] is not None:
    print(result["finalTone"]["name"])
    print(result["tuningStatus"])  # inTune or needsTuning
else:
    print("Strum again")
```

The detector accepts finite mono PCM at 8–192 kHz, lasting 0.4–8 seconds. It analyzes a copy and does not record, save, or upload audio.

### Get a generated tone

```python
from pathlib import Path
from baglama_sound_ml.audio import write_wav
from baglama_sound_ml.synthesis import neural

audio, details = neural(
    Path("models/my-model.npz"),
    hz=146.8323839587038,  # D3, A4 = 440 Hz
    course="alt",        # ust = upper, orta = middle, alt = lower
    duration=0.8,
    seed=7,
)
write_wav(Path("outputs/D3.wav"), audio)
```

This returns mono PCM at 48 kHz. Pitch is supplied explicitly; the small model predicts harmonic/noise envelopes and DSP synthesizes the waveform. It does not retrieve an original recording. The separate nearest-sample baseline does require source recordings.

## Train your own model

Use your own compatible real-recording packs. The local sample library imports Baglamator-style ZIPs containing paired `.json` metadata and `.f32` mono PCM. See [the data format](data-format.md).

```sh
# After importing/reviewing samples in the playground:
make train
make compare
make restart
```

Training exports the active sample library, prepares/deduplicates recordings, trains a separate model, and creates reference/sample/neural listening comparisons. Each run preserves earlier versions. `make restart` selects the latest successful run automatically.

Defaults: 600 steps, seed 7, with the Sol-sharp final-tone variant reserved for checkpoint validation. Both training and validation data, including all three training courses, are required. Generated-sound feedback can give bounded emphasis to nearby real targets; generated PCM never becomes ground truth. `make train FEEDBACK=0` gives a real-only control. Validation selects the checkpoint and is not an independent final test. More steps or more recordings do not guarantee better timbre.

## Commands and checks

Run `make` or `make help` for commands. See [COMMANDS.md](../COMMANDS.md) for options.

```sh
make test
node --test tests/*.test.cjs
swift test -Xswiftc -warnings-as-errors
```

JavaScript tests require Node.js with the built-in test runner. Tests create synthetic/temp fixtures; personal recordings and trained models are not required. The local synthesis-training integration test uses optional PyTorch when installed.

## Repository and privacy

- `Sources/`: lightweight Swift runtime and optional render executable.
- `src/`: Python detection, synthesis, training, storage and local web tools.
- `tests/`, `scripts/`, `docs/`: reproducible development tools and documentation.
- `data/`, `models/`, `outputs/`: local-only, Git-ignored artifacts.

The local server binds to loopback and requires same-origin/token checks for writes. Captures are foreground-only and bounded. Audio is retained only through explicit save actions; microphone clips can otherwise remain temporarily in browser memory for replay. Recordings, labels, feedback, databases, model versions and generated reports stay out of Git. The public repository contains no pretrained model: do not assume a clone reproduces private training results.
