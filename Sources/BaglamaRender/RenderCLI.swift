import Foundation
import BaglamaSoundML

@main
struct RenderCLI {
    static func main() throws {
        let arguments = Array(CommandLine.arguments.dropFirst())
        guard arguments.count == 4,
              let frequency = Double(arguments[1]),
              let course = BaglamaCourse(rawValue: arguments[2]) else {
            print("Usage: BaglamaRender MODEL.json FREQUENCY_HZ ust|orta|alt OUTPUT.wav")
            return
        }
        let model = try BaglamaModel(contentsOf: URL(fileURLWithPath: arguments[0]))
        let request = try SynthesisRequest(frequencyHertz: frequency, course: course)
        let audio = try BaglamaSynthesizer(model: model).render(request)
        try audio.wavData().write(to: URL(fileURLWithPath: arguments[3]))
        let controls = try model.controls(frequencyHertz: frequency, course: course, timeSeconds: 0.2)
        print(String(decoding: try JSONEncoder().encode(controls), as: UTF8.self))
    }
}
