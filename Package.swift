// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "BaglamaSoundML",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [
        .library(name: "BaglamaSoundML", targets: ["BaglamaSoundML"]),
        .executable(name: "BaglamaRender", targets: ["BaglamaRender"])
    ],
    targets: [
        .target(name: "BaglamaSoundML"),
        .executableTarget(name: "BaglamaRender", dependencies: ["BaglamaSoundML"]),
        .testTarget(name: "BaglamaSoundMLTests", dependencies: ["BaglamaSoundML"],
                    path: "tests/BaglamaSoundMLTests")
    ]
)
