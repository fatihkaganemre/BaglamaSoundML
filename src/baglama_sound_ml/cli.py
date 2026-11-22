from __future__ import annotations
from pathlib import Path
import argparse
import json
import math
from .audio import COURSES, frequency, validate_request, write_wav
from .dataset import import_packs
from .neural import train
from .report import compare
from .synthesis import sample, neural
from .export import export_swift, playground


def main():
    parser = argparse.ArgumentParser(description="Local bağlama synthesis and neural timbre experiments")
    sub = parser.add_subparsers(dest="command", required=True)
    importer = sub.add_parser("import", help="Prepare and deduplicate local TuneAI ZIP recordings")
    importer.add_argument("--source", type=Path, required=True)
    importer.add_argument("--out", type=Path, default=Path("data/recordings"))
    trainer = sub.add_parser("train", help="Train a small harmonic-envelope MLP on CPU")
    trainer.add_argument("--dataset", type=Path, default=Path("data/recordings"))
    trainer.add_argument("--out", type=Path, default=Path("models/baglama.npz"))
    trainer.add_argument("--steps", type=int, default=600)
    trainer.add_argument("--holdout-variant", default="karar-G-sharp")
    trainer.add_argument("--seed", type=int, default=7)
    renderer = sub.add_parser("render", help="Generate a note with explicit octave and optional cents")
    renderer.add_argument("--method", choices=("sample", "neural"), default="sample")
    target = renderer.add_mutually_exclusive_group(required=True)
    target.add_argument("--note", help="Scientific pitch, e.g. 'G#2', A2, Db3")
    target.add_argument("--hz", type=float)
    renderer.add_argument("--course", choices=COURSES, required=True)
    renderer.add_argument("--duration", type=float, default=0.8)
    renderer.add_argument("--cents", type=float, default=0)
    renderer.add_argument("--reference", type=float, default=440)
    renderer.add_argument("--dataset", type=Path, default=Path("data/recordings"))
    renderer.add_argument("--model", type=Path, default=Path("models/baglama.npz"))
    renderer.add_argument("--seed", type=int, default=7)
    renderer.add_argument("--out", type=Path, required=True)
    reporter = sub.add_parser("compare", help="Render a local HTML report on held-out recordings")
    reporter.add_argument("--dataset", type=Path, default=Path("data/recordings"))
    reporter.add_argument("--model", type=Path, default=Path("models/baglama.npz"))
    reporter.add_argument("--out", type=Path, default=Path("outputs/comparison"))
    continuation = sub.add_parser("continue-note", help="Predict and score the second half of held-out plucks")
    continuation.add_argument("--dataset", type=Path)
    continuation.add_argument("--model", type=Path)
    continuation.add_argument("--out", type=Path, required=True)
    for name, help_text, default in (
        ("export-swift", "Export a model for the Swift package", "models/baglama.swift.json"),
        ("playground", "Build a standalone browser synthesizer", "outputs/playground/index.html"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--model", type=Path, default=Path("models/baglama.npz"))
        command.add_argument("--out", type=Path, default=Path(default))
    server = sub.add_parser("serve", help="Run the local recording library and feedback workspace")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--stop", action="store_true", help="Stop this project's existing local server")
    server.add_argument("--library", type=Path, default=Path("data/library"))
    server.add_argument("--model", type=Path, default=Path("models/baglama.npz"))
    server.add_argument("--dataset", type=Path, default=Path("data/recordings"), help="Prepared training dataset used by the sample baseline")
    server.add_argument("--samples", type=Path, default=Path("../TuneAI/samples"))
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from .local_server import serve, stop_server
            if args.stop:
                stop_server(Path.cwd(),args.port)
                return
            serve(Path.cwd(), args.library, args.model, args.samples, args.port, args.dataset)
            return
        elif args.command == "export-swift":
            result = export_swift(args.model, args.out)
        elif args.command == "playground":
            result = playground(args.model, args.out)
        elif args.command == "import":
            report = import_packs(args.source, args.out)
            result = {key: value for key, value in report.items() if key != "recordings"}
        elif args.command == "train":
            report = train(args.dataset, args.out, args.steps, args.holdout_variant, args.seed)
            result = {key: report[key] for key in ("parameters", "training_count", "validation_count", "best_validation_normalized_mse")}
        elif args.command == "compare":
            report = compare(args.dataset, args.model, args.out)
            result = dict(recordings=report["recordings"], report=str(args.out/"index.html"))
        elif args.command == "continue-note":
            from .continuation import compare_continuations
            if (args.dataset is None) != (args.model is None):
                raise ValueError("Specify both --dataset and --model, or use the latest local training run.")
            if args.model is None:
                latest = json.loads(Path("models/latest-training.json").read_text())
                args.dataset, args.model = Path(latest["dataset"]), Path(latest["model"])
            report = compare_continuations(args.dataset, args.model, args.out)
            result = dict(recordings=report["recordings"], skipped=len(report["skipped"]),
                          report=str(args.out / "index.html"))
        else:
            if not math.isfinite(args.cents) or abs(args.cents) > 1200:
                raise ValueError("Cents offset must be finite and within ±1200.")
            hz = (frequency(args.note, args.reference) if args.note else args.hz) * 2**(args.cents/1200)
            validate_request(hz, args.duration)
            if args.method == "sample":
                audio, result = sample(args.dataset, hz, args.course, args.duration)
            else:
                audio, result = neural(args.model, hz, args.course, args.duration, args.seed)
            write_wav(args.out, audio)
            result.update(requested_hz=hz, course=args.course, duration=args.duration, output=str(args.out))
            args.out.with_suffix(".json").write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, OverflowError) as error:
        parser.exit(2, f"Error: {error}\n")
