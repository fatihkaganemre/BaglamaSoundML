"""Small, deterministic PCM and pitch utilities; no microphone or network I/O."""
from __future__ import annotations
from pathlib import Path
import math
import wave
import numpy as np

RATE = 48_000
COURSES = ("ust", "orta", "alt")


def frequency(note: str, reference: float = 440) -> float:
    """Parse an explicit scientific-pitch note, e.g. G#2, Db3, A4."""
    import re
    match = re.fullmatch(r"([A-Ga-g])([#b♯♭]?)(-?\d+)", note)
    if not match or not math.isfinite(reference) or reference <= 0:
        raise ValueError("Use a note with an explicit octave (e.g. G#2), and a positive reference.")
    letter, accidental, octave = match.groups()
    semitone = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)[letter.upper()]
    semitone += 1 if accidental in ("#", "♯") else -1 if accidental in ("b", "♭") else 0
    return reference * 2 ** (((int(octave) + 1) * 12 + semitone - 69) / 12)


def validate_request(hz: float, duration: float) -> None:
    if not math.isfinite(hz) or not 40 <= hz <= 2000:
        raise ValueError("Frequency must be finite and between 40 and 2000 Hz.")
    if not math.isfinite(duration) or not 0.1 <= duration <= 3:
        raise ValueError("Duration must be finite and between 0.1 and 3 seconds.")


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
            raise ValueError("Expected a mono 16-bit PCM WAV.")
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float64) / 32768, stream.getframerate()


def write_wav(path: Path, audio: np.ndarray, rate: int = RATE) -> None:
    if audio.ndim != 1 or not len(audio) or not np.all(np.isfinite(audio)):
        raise ValueError("Audio must be a nonempty finite mono waveform.")
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.round(np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(pcm.tobytes())


def finish(audio: np.ndarray, rate: int = RATE) -> np.ndarray:
    """Bound output headroom and fade edges; never amplify numerical silence."""
    audio = np.asarray(audio, dtype=np.float64).copy()
    audio -= audio.mean()
    peak = np.max(np.abs(audio))
    if peak < 1e-8:
        raise ValueError("Cannot export a silent result.")
    audio *= 0.8 / peak
    fade = min(int(rate * 0.01), len(audio) // 4)
    audio[:fade] *= np.linspace(0, 1, fade)
    audio[-fade:] *= np.linspace(1, 0, fade)
    return audio


def pitch(audio: np.ndarray, rate: int = RATE) -> float | None:
    """Independent YIN-style period check; may report ambiguity on noisy plucks."""
    size = min(len(audio), 6144)
    if size < 2048:
        return None
    x = np.array(audio[:size], dtype=np.float64, copy=True)
    x -= x.mean()
    if np.sqrt(np.mean(x*x)) < 1e-5:
        return None
    window = size // 2
    upper = min(window - 1, int(rate / 40))
    lower = max(2, int(rate / 2000))
    difference = np.zeros(upper + 1)
    for lag in range(1, upper + 1):
        delta = x[:window] - x[lag:lag + window]
        difference[lag] = np.dot(delta, delta)
    normalized = np.ones_like(difference)
    normalized[1:] = difference[1:] * np.arange(1, upper + 1) / np.maximum(np.cumsum(difference[1:]), 1e-20)
    candidates = [i for i in range(lower, upper) if normalized[i] < 0.15 and normalized[i] <= normalized[i-1] and normalized[i] < normalized[i+1]]
    if not candidates:
        return None
    index = candidates[0]
    left, center, right = normalized[index-1:index+2]
    denominator = left - 2*center + right
    lag = index + (0.5*(left-right)/denominator if abs(denominator) > 1e-12 else 0)
    return rate / lag
