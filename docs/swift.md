# Swift integration

The current package requires **Swift 6**, supports **iOS 16+ / macOS 13+**, and has no third-party runtime dependencies.

In Xcode, add this repository as a package dependency and select the **BaglamaSoundML** library product. For a local checkout, add the project directory as a local package. Choose a published tag for a reproducible build. See [using published versions](releases.md).

Download a portable model from the matching release when available, or export your own:

```sh
.venv/bin/python3 -m baglama_sound_ml export-swift \
  --model models/my-model.npz \
  --out outputs/baglama.swift.json
```

Add that JSON file to your application's resources, then call the existing synthesis API:

```swift
import Foundation
import BaglamaSoundML

// Supply the URL of your application's exported model resource.
let model = try BaglamaModel(contentsOf: modelURL)
let synthesizer = BaglamaSynthesizer(model: model)
let request = try SynthesisRequest(
    frequencyHertz: 146.8323839587038,
    course: .lower,
    durationSeconds: 0.8,
    seed: 7
)
let pcm = try synthesizer.render(request)
// pcm.samples: [Float], mono, BaglamaPCM.sampleRate == 48_000.
// pcm.wavData() encodes a WAV if your app needs one.
```

Load/render off the audio callback. Your application owns microphone permission, audio sessions, playback, interruptions, and route changes. Neither the Swift library nor importing the Python package starts recording.

**Swift final-tone detection and the final convenience API are future work.** The intended interaction is “pass PCM, get a detection result” or “request a tone, get PCM”; there is no Swift `detectFinalTone` function today. The working Python detector will be evaluated before porting. Python, PyTorch, the web playground, samples and test-case databases are not bundled by SPM. Only your chosen exported model needs to accompany synthesis; its size depends on the model/export format.
