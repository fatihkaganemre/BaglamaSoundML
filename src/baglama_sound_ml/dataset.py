"""Import owner-provided TuneAI ZIPs without extracting paths or retaining personal metadata."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import math
import zipfile
import numpy as np
from .audio import COURSES, RATE, finish, write_wav


def load_dataset(directory: Path) -> list[dict]:
    rows = json.loads((directory / "manifest.json").read_text())["recordings"]
    root = directory.resolve()
    for row in rows:
        resolved = (root / row["file"]).resolve()
        if root not in resolved.parents:
            raise ValueError("Dataset contains an escaping audio path.")
    return rows


def import_packs(source: Path, destination: Path) -> dict:
    if (destination / "manifest.json").exists():
        raise ValueError("Dataset already exists; choose a new output directory to preserve it.")
    rows, seen, skipped = [], set(), {}
    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1
    for archive in sorted(source.rglob("*.zip")):
        with zipfile.ZipFile(archive) as pack:
            for name in sorted(pack.namelist()):
                if not name.endswith(".json") or name.startswith("__MACOSX/"):
                    continue
                if pack.getinfo(name).file_size > 1_000_000:
                    raise ValueError("Sample metadata is unexpectedly large.")
                metadata = json.loads(pack.read(name))
                if "audioFormat" not in metadata:
                    continue
                label = metadata.get("label", {})
                analysis = metadata.get("pitchAnalysis", {})
                string_id = label.get("stringID", "")
                parts = string_id.split(".")
                if label.get("instrumentID") != "kisaSap" or label.get("tuningID") != "baglama" or len(parts) != 4 or parts[-2] not in COURSES:
                    skip("unsupported_instrument_or_tuning")
                    continue
                hz = analysis.get("estimatedFrequencyHertz", 0)
                if analysis.get("quality") != "consistent" or not isinstance(hz, (int, float)) or not math.isfinite(hz) or not 40 <= hz <= 2000:
                    skip("uncertain_or_missing_pitch")
                    continue
                rate = metadata.get("sampleRate")
                if metadata.get("audioFormat") != "pcm_f32le_mono" or rate != RATE:
                    skip("unsupported_audio_format")
                    continue
                target = label.get("target", {})
                note = target.get("note")
                if not isinstance(note, int) or not 0 <= note <= 11:
                    skip("invalid_note_label")
                    continue
                measured_midi = 69 + 12 * math.log2(hz / 440)
                deviation = (measured_midi - note + 6) % 12 - 6
                if abs(deviation * 100) > 35:
                    skip("pitch_label_disagreement")
                    continue
                audio_name = str(Path(name).with_suffix(".f32"))
                if audio_name not in pack.namelist():
                    skip("missing_audio")
                    continue
                info = pack.getinfo(audio_name)
                if info.file_size > RATE * 4 * 30:
                    raise ValueError("A capture exceeds the 30-second import limit.")
                raw = pack.read(audio_name)
                identity = hashlib.sha256(raw).hexdigest()
                if identity in seen:
                    skip("duplicate_waveform")
                    continue
                audio = np.frombuffer(raw, dtype="<f4").astype(np.float64)
                if len(audio) < RATE // 4 or not np.all(np.isfinite(audio)):
                    skip("invalid_audio")
                    continue
                audio -= audio.mean()
                peak = np.max(np.abs(audio))
                if peak < 1e-5:
                    skip("silent_audio")
                    continue
                onset = int(np.flatnonzero(np.abs(audio) >= peak * 0.1)[0])
                start = max(0, onset - int(RATE * 0.002))
                audio = audio[start:start + RATE]
                if len(audio) < RATE // 3:
                    skip("short_pluck")
                    continue
                relative = f"audio/{identity[:24]}.wav"
                write_wav(destination / relative, finish(audio))
                seen.add(identity)
                rows.append(dict(file=relative, identity=identity, frequency_hz=hz,
                                 course=parts[-2], physical_string=parts[-1],
                                 variant=label.get("variantID", "unknown"),
                                 duration=len(audio)/RATE, pitch_class=note))
    if not rows:
        raise ValueError("No eligible TuneAI recordings found.")
    report = dict(schema_version=1, sample_rate=RATE, recordings=rows,
                  imported_count=len(rows), prepared_seconds=sum(r["duration"] for r in rows), skipped=skipped)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
