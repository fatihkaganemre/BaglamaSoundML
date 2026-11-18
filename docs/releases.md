# Using published package versions

Official versions are published by the repository owner. Using the package does not require repository write access, release permissions, or a GitHub personal access token.

In Xcode, add `https://github.com/fatihkaganemre/BaglamaSoundML.git`, select the **BaglamaSoundML** product, and choose a published version from the repository's [Releases](https://github.com/fatihkaganemre/BaglamaSoundML/releases). Until a version exists, the default branch can be used for experimentation.

After an example version `0.1.0` has actually been published, another Swift package can declare:

```swift
.package(
    url: "https://github.com/fatihkaganemre/BaglamaSoundML.git",
    from: "0.1.0"
)
```

Add `.product(name: "BaglamaSoundML", package: "BaglamaSoundML")` to your target dependencies. Inspect the README at the chosen version for available APIs and supported platforms. An exact version requirement can be used when reproducibility is needed.

Releases contain source code, not private recordings, trained weights, feedback databases, or generated audio. The app supplies its own portable model for synthesis. Python research tools do not ship inside the Swift runtime, and a release does not make unfinished Swift APIs available.

Public users may clone/fork the project and propose changes through pull requests; this does not grant write access to this repository or permission to publish its official releases.
