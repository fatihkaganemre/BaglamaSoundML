# SPM versions and GitHub releases

Swift Package Manager resolves semantic-version **Git tags**; a GitHub release is the human-facing description of a tag. This repository uses stable tags of the form `vMAJOR.MINOR.PATCH`, such as `v0.1.0`. Prerelease suffixes are not configured yet.

## What CI checks

CI runs for pull requests and pushes to `main`, and can be dispatched manually. It tests the Swift runtime on macOS, builds release products and the iOS simulator runtime, tests Python 3.9 and 3.12 (including CPU training integration on 3.12), and runs the browser controller/worklet tests on Node 22. No personal recordings, pretrained weights or secrets are required.

Release tags reuse the same checks. Only the final publishing job has `contents: write`; other jobs have read-only repository permissions. Official actions are pinned to immutable commits. The workflow uses GitHub's ephemeral token rather than a personal access token.

Run `make release-help` for a quick reminder. It prints instructions and never creates a tag.

## Release a version

1. Update `[project].version` in `pyproject.toml` to the version being released, such as `0.1.0`. SPM reads the Git tag; this check keeps source-package metadata aligned.
2. Update API documentation/release notes and merge or push the intended commit to `main` through your normal review process.
3. Wait for **CI** to pass for that exact commit. Start from a clean, up-to-date checkout:

   ```sh
   git switch main
   git pull --ff-only origin main
   git status --short
   ```

4. Create and push **only the intended version tag** (replace the example for later releases):

   ```sh
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin v0.1.0
   ```

5. Watch **Release** in GitHub Actions. It validates the tag against `pyproject.toml`, requires the tagged commit to belong to `main`, reruns CI, and creates a source release with generated notes. Rerunning an already published tag leaves its release unchanged.

**Important:** pushing a valid Git tag makes it discoverable to SPM immediately, even before the GitHub release workflow finishes. CI gates the GitHub release, not visibility of the tag itself. Check CI before tagging. Never move/reuse a published version tag; release a new version for fixes.

The workflow does not upload local build directories, model files, sample packs, databases, or reports. GitHub's automatic source archives contain the tracked repository files. Keeping artifacts Git-ignored remains essential.

No first release/tag is created just by installing these workflows. The first version can be published when the maintainer explicitly tags it.

## Consume a version

In Xcode, add the repository URL and choose an appropriate version requirement. In another Swift package, after the example version exists:

```swift
.package(
    url: "https://github.com/fatihkaganemre/BaglamaSoundML.git",
    from: "0.1.0"
)
```

Then depend on `.product(name: "BaglamaSoundML", package: "BaglamaSoundML")`. Inspect the README at the chosen tag: a release does not make unfinished APIs available. Model artifacts are supplied separately by the consuming app.

## References

- [SwiftPM versioned dependencies](https://docs.swift.org/package-manager/PackageDescription/PackageDescription.html)
- [GitHub's Swift CI guide](https://docs.github.com/en/actions/tutorials/build-and-test-code/swift)
- [GitHub CLI release creation and tag verification](https://cli.github.com/manual/gh_release_create)
