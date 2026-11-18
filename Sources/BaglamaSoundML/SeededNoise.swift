import Foundation

/// Portable xorshift32 for reproducible browser/Swift phases and attack noise.
struct SeededNoise: Sendable {
    private var state: UInt32

    init(seed: UInt32) { state = seed == 0 ? 7 : seed }

    mutating func uniform() -> Double {
        state ^= state << 13
        state ^= state >> 17
        state ^= state << 5
        return (Double(state) + 0.5) / 4_294_967_296
    }

    mutating func gaussian() -> Double {
        sqrt(-2 * log(uniform())) * cos(2 * .pi * uniform())
    }
}
