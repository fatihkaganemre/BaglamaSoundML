# Local real-recording packs

The sample library accepts ZIP files with paired JSON metadata and float32 little-endian mono PCM:

```text
Samples/
  take-001.json
  take-001.f32
```

The JSON and audio must have the same stem. Example metadata for a verified A2 upper-course target:

```json
{
  "audioFormat": "pcm_f32le_mono",
  "sampleRate": 48000,
  "sessionID": "session-001",
  "label": {
    "instrumentID": "kisaSap",
    "tuningID": "baglama",
    "variantID": "karar-A",
    "stringID": "kisaSap.baglama.ust.1",
    "target": { "note": 9, "octave": 2 }
  },
  "pitchAnalysis": {
    "quality": "consistent",
    "estimatedFrequencyHertz": 110.0
  }
}
```

This is a format illustration, not an audio fixture. Supply your own recordings and genuine measured analysis. Target note is a pitch class: C=0 through B=11. Octave is optional and must not be guessed. A labeled target and a pitch estimate are distinct from independently verified ground truth. Catalog identifiers are in `src/baglama_sound_ml/resources/capture-catalog.json`.

The library preserves uncertain recordings for review. The synthesis importer is stricter: currently 48 kHz, Kısa Sap / Bağlama Düzeni, recognized course IDs, consistent pitch estimates and pitch-class agreement. It deduplicates raw waveforms, aligns pluck onset and prepares up to one second of audio. Inspect the import summary; importing a ZIP into the library does not itself train a model.

Final-tone evaluation exports are a different format: `cases/*.json` plus `cases/*.f32`, with known final tone, per-string annotations and original detector output. They are not synthesis training packs. Keep related takes/session groups separated when designing independent evaluations; exact hash deduplication alone cannot prevent all leakage.
