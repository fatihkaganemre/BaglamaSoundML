import Foundation
import Testing
@testable import BaglamaSoundML

struct BaglamaSoundMLTests {
    private func fixtureData() throws -> Data {
        let dimensions = [(5, 48), (48, 48), (48, 25)]
        let layers: [[String: Any]] = dimensions.map { inputs, outputs in
            ["weights": Array(repeating: Array(repeating: 0.0, count: inputs), count: outputs),
             "biases": Array(repeating: 0.0, count: outputs)]
        }
        var mean = Array(repeating: -14.0, count: 25)
        mean[0] = -1
        return try JSONSerialization.data(withJSONObject: [
            "schemaVersion": 1, "layers": layers, "mean": mean,
            "scale": Array(repeating: 1.0, count: 25),
            "frequencyRangesHz": ["ust": [80.0, 220.0], "orta": [170.0, 200.0], "alt": [130.0, 300.0]]
        ])
    }

    @Test func predictsKnownControlsAndTrainingRange() throws {
        let model = try BaglamaModel(data: fixtureData())
        let controls = try model.controls(frequencyHertz: 110, course: .upper, timeSeconds: 0.2)
        #expect(controls.count == 25)
        #expect(abs(controls[0] - exp(-1)) < 1e-12)
        #expect(model.trainingRange(for: .upper) == 80...220)
    }

    @Test func rejectsInvalidRequestsAndModelShape() throws {
        #expect(throws: BaglamaError.self) { try SynthesisRequest(frequencyHertz: .nan, course: .upper) }
        #expect(throws: BaglamaError.self) { try SynthesisRequest(frequencyHertz: 110, course: .upper, durationSeconds: 0) }
        let invalid = try JSONSerialization.data(withJSONObject: ["schemaVersion": 1, "layers": [], "mean": [], "scale": [], "frequencyRangesHz": [:]])
        #expect(throws: BaglamaError.self) { try BaglamaModel(data: invalid) }
    }

    @Test func rendersDeterministicPitchWithHeadroomAndWAV() throws {
        let model = try BaglamaModel(data: fixtureData())
        let synth = BaglamaSynthesizer(model: model)
        let request = try SynthesisRequest(frequencyHertz: 110, course: .upper, durationSeconds: 0.5)
        let audio = try synth.render(request)
        let again = try synth.render(request)
        #expect(audio.samples == again.samples)
        #expect(audio.samples.count == 24_000)
        #expect(audio.samples.allSatisfy { $0.isFinite && abs($0) <= 0.800001 })
        #expect(audio.samples.first == 0)
        #expect(audio.samples.last == 0)
        let crossings = (1000..<23_000).filter { audio.samples[$0 - 1] < 0 && audio.samples[$0] >= 0 }
        guard let first = crossings.first, let last = crossings.last else {
            Issue.record("Expected positive zero crossings")
            return
        }
        let measured = Double(crossings.count - 1) * 48_000 / Double(last - first)
        #expect(abs(measured - 110) < 0.1)
        let wav = audio.wavData()
        #expect(wav.count == 44 + 48_000)
        #expect(String(decoding: wav.prefix(4), as: UTF8.self) == "RIFF")
    }
}
