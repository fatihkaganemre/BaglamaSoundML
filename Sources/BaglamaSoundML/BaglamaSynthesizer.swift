import Foundation

/// Offline synthesis. Render away from the main actor and real-time audio callbacks.
/// The caller owns playback, audio-session lifecycle, and cancellation of its work.
public struct BaglamaSynthesizer: Sendable {
    public let model: BaglamaModel
    public init(model: BaglamaModel) { self.model = model }

    public func render(_ request: SynthesisRequest) throws -> BaglamaPCM {
        let rate = Double(BaglamaPCM.sampleRate)
        let count = Int((request.durationSeconds * rate).rounded())
        let frames = max(16, Int((request.durationSeconds * 100).rounded()))
        let times = (0..<frames).map { Double($0) * request.durationSeconds / Double(frames - 1) }
        let controls = times.map {
            model.predict(frequencyHertz: request.frequencyHertz, course: request.course, timeSeconds: $0)
        }
        func interpolate(_ index: Int, at time: Double) -> Double {
            let frame = max(0, min(frames - 2, Int(time / request.durationSeconds * Double(frames - 1))))
            let fraction = max(0, min(1, (time - times[frame]) / (times[frame + 1] - times[frame])))
            return controls[frame][index] * (1 - fraction) + controls[frame + 1][index] * fraction
        }
        var random = SeededNoise(seed: request.seed)
        let phases = (0..<24).map { _ in random.uniform() * 2 * .pi - .pi }
        var noise = [Double](repeating: 0, count: count)
        var highPass = 0.0, lowPass = 0.0, previous = 0.0, energy = 0.0
        let highCoefficient = exp(-2 * .pi * 2000 / rate)
        let lowCoefficient = 1 - exp(-2 * .pi * 9000 / rate)
        for index in noise.indices {
            let white = random.gaussian()
            highPass = highCoefficient * (highPass + white - previous)
            previous = white
            lowPass += lowCoefficient * (highPass - lowPass)
            noise[index] = lowPass
            energy += lowPass * lowPass
        }
        let noiseScale = max(sqrt(energy / Double(count)), 1e-8)
        var audio = [Double](repeating: 0, count: count)
        var mean = 0.0
        for index in audio.indices {
            if index % 4096 == 0 { try Task.checkCancellation() }
            let time = Double(index) / rate
            var value = 0.0
            for harmonic in 1...24 {
                let frequency = Double(harmonic) * request.frequencyHertz
                guard frequency < rate * 0.48 else { break }
                value += interpolate(harmonic - 1, at: time) * sin(2 * .pi * frequency * time + phases[harmonic - 1])
            }
            value += noise[index] / noiseScale * interpolate(24, at: time) * 0.2
            value *= exp(-4 * max(time - 1, 0))
            audio[index] = value
            mean += value
        }
        mean /= Double(count)
        var peak = 0.0
        for index in audio.indices {
            audio[index] -= mean
            peak = max(peak, abs(audio[index]))
        }
        guard peak >= 1e-8 else { throw BaglamaError.silentOutput }
        let fade = min(Int(rate * 0.01), count / 4)
        let samples = audio.indices.map { index -> Float in
            var gain = 0.8 / peak
            if index < fade { gain *= Double(index) / Double(fade - 1) }
            if index >= count - fade { gain *= Double(count - 1 - index) / Double(fade - 1) }
            return Float(audio[index] * gain)
        }
        return BaglamaPCM(samples: samples)
    }
}
