import Foundation

struct ModelDocument: Decodable, Sendable {
    struct Layer: Decodable, Sendable {
        let weights: [[Double]]
        let biases: [Double]
    }
    let schemaVersion: Int
    let layers: [Layer]
    let mean: [Double]
    let scale: [Double]
    let frequencyRangesHz: [String: [Double]]

    func validate() throws {
        guard schemaVersion == 1, layers.count == 3,
              mean.count == 25, scale.count == 25,
              mean.allSatisfy(\.isFinite), scale.allSatisfy({ $0.isFinite && $0 > 0 }) else {
            throw BaglamaError.invalidModel
        }
        let dimensions = [(5, 48), (48, 48), (48, 25)]
        for (layer, (inputs, outputs)) in zip(layers, dimensions) {
            guard layer.weights.count == outputs, layer.biases.count == outputs,
                  layer.biases.allSatisfy(\.isFinite),
                  layer.weights.allSatisfy({ $0.count == inputs && $0.allSatisfy(\.isFinite) }) else {
                throw BaglamaError.invalidModel
            }
        }
        for course in BaglamaCourse.allCases {
            guard let range = frequencyRangesHz[course.rawValue], range.count == 2,
                  range.allSatisfy(\.isFinite), range[0] > 0, range[0] <= range[1] else {
                throw BaglamaError.invalidModel
            }
        }
    }
}
