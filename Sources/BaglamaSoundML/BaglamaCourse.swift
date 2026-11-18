/// Physical string course; pitch/register is always supplied separately.
public enum BaglamaCourse: String, Codable, CaseIterable, Sendable {
    case upper = "ust"
    case middle = "orta"
    case lower = "alt"
}
