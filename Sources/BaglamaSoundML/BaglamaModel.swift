import Foundation

/// Immutable, portable MLP weights. No model or private recordings are bundled.
public struct BaglamaModel: Sendable {
    private let document: ModelDocument

    /// Load the JSON produced by Python's `export-swift` command, off the audio thread.
    public init(data: Data) throws {
        let decoded = try JSONDecoder().decode(ModelDocument.self, from: data)
        try decoded.validate()
        document = decoded
    }

    public init(contentsOf url: URL) throws {
        try self.init(data: Data(contentsOf: url))
    }

    public func trainingRange(for course: BaglamaCourse) -> ClosedRange<Double>? {
        guard let bounds = document.frequencyRangesHz[course.rawValue] else { return nil }
        return bounds[0]...bounds[1]
    }

    /// Twenty-four harmonic amplitudes and one residual-noise amplitude.
    /// Pitch within the training range still does not imply validated timbre coverage.
    public func controls(frequencyHertz: Double, course: BaglamaCourse,
                         timeSeconds: Double) throws -> [Double] {
        guard frequencyHertz.isFinite, (40...2000).contains(frequencyHertz),
              timeSeconds.isFinite, (0...3).contains(timeSeconds) else {
            throw BaglamaError.invalidRequest
        }
        return predict(frequencyHertz: frequencyHertz, course: course, timeSeconds: timeSeconds)
    }

    func predict(frequencyHertz: Double, course: BaglamaCourse, timeSeconds: Double) -> [Double] {
        var values = [min(timeSeconds, 1), log2(frequencyHertz / 196)] +
            BaglamaCourse.allCases.map { $0 == course ? 1.0 : 0.0 }
        for (index, layer) in document.layers.enumerated() {
            let previous = values
            values = layer.weights.enumerated().map { row, weights in
                var value = layer.biases[row]
                for column in weights.indices { value += weights[column] * previous[column] }
                return index == document.layers.count - 1 ? value :
                    value / (1 + exp(-max(-60, min(60, value))))
            }
        }
        return values.indices.map { index in
            exp(max(-14, min(0, values[index] * document.scale[index] + document.mean[index])))
        }
    }
}
