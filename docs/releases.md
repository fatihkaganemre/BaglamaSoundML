# Published versions

Find version tags and any accompanying model downloads on [GitHub Releases](https://github.com/fatihkaganemre/BaglamaSoundML/releases).

Use the corresponding semantic version in Xcode or in your Swift package:

```swift
.package(
    url: "https://github.com/fatihkaganemre/BaglamaSoundML.git",
    from: "0.1.0"
)
```

Add `.product(name: "BaglamaSoundML", package: "BaglamaSoundML")` to your target dependencies. Use an exact version requirement when you need a reproducible build.

The Swift package takes a portable JSON model provided by your app. When a release offers a model, download its JSON separately and add it to your app’s resources. You can also [export your own model](swift.md). A portable export contains inference parameters and frequency ranges. Original recordings, training manifests, feedback databases, and generated audio stay local.

The repository owner publishes official versions. Installing the package requires only read access.
