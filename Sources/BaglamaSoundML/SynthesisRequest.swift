import Foundation

public struct SynthesisRequest: Sendable {
    public let frequencyHertz: Double
    public let course: BaglamaCourse
    public let durationSeconds: Double
    public let seed: UInt32

    /// Supply an absolute frequency, including any reference-pitch/cents adjustment.
    public init(frequencyHertz: Double, course: BaglamaCourse,
                durationSeconds: Double = 0.8, seed: UInt32 = 7) throws {
        guard frequencyHertz.isFinite, (40...2000).contains(frequencyHertz),
              durationSeconds.isFinite, (0.1...3).contains(durationSeconds) else {
            throw BaglamaError.invalidRequest
        }
        self.frequencyHertz = frequencyHertz
        self.course = course
        self.durationSeconds = durationSeconds
        self.seed = seed
    }
}
