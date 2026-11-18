# Runtime and research boundaries

## Synthesis

Training fits a small pitch/course/time-conditioned network to harmonic and noise envelopes extracted from real plucks. Python saves a training checkpoint. `export-swift` emits only inference weights and frequency ranges, excluding recording identities and training paths.

Swift loads this exported model and synthesizes 48 kHz mono PCM using oscillators, interpolated envelopes and a seeded noise residual. It does not require the original recordings or a Python runtime. The nearest-sample research baseline is separate and needs its source recordings.

Pitch is controlled explicitly by DSP; accurate oscillator frequency is not proof of realistic timbre. The model describes a simplified pluck, not full playing technique or a sustained performance. Actual app-size and device performance must be measured in the consuming application's release build.

## Final-tone analysis

The current Python prototype analyzes a bounded copy of the strum with windowed FFTs, spectral peak interpolation and harmonic suppression. It scores the observed pitch classes against catalog course patterns. Acceptance requires support from all three course pitch classes and a margin over alternatives. A tuning-consistency check distinguishes a clear/tuned result from a recognizable pattern needing adjustment. Ambiguous data causes abstention.

It is a heuristic signal-processing baseline, not a trained classifier. Only Kısa Sap / Bağlama Düzeni is currently supported. Physical strings, missing fundamentals, room acoustics and octave partners can remain unresolved. No real-world accuracy guarantee follows from synthetic tests. The Swift analysis API is not implemented yet.

## Local application and data

Browser microphone capture is explicit, foreground-only and bounded. Tracks stop before analysis; cancellation, navigation and interruption stop capture. The loopback server validates origin and per-run tokens for writes. Audio remains local, and saving audio requires a separate explicit save action.

The synthesis library, generated-sound feedback and strum evaluation cases are separate collections. Saved strums retain owner labels and original detector output; they do not enter synthesis training. Development cases that influence algorithm changes must not be described as independent final tests.

## Distribution

`Package.swift` declares the Swift targets explicitly. Python code, web assets, research scripts, datasets, reports and tests are not application resources. The current library bundles no trained model: the consuming app supplies one selected portable export. Training checkpoints and recordings remain local and Git-ignored.

The desired future interaction is deliberately small: supply audio and receive a detection result, or request a pitched tone and receive PCM. Public Swift detection signatures and product separation will be designed after validating the prototype, rather than documenting nonexistent functions as working APIs.
