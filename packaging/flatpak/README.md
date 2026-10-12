# Flatpak and Flathub

`io.github.phosphene_dev.Hallucinate.yml` builds Hallucinate on the KDE 6.11 runtime with the
[PySide BaseApp](https://github.com/flathub/io.qt.PySide.BaseApp) (PySide6 and numpy). The remaining
Python dependencies are pinned with checksums in `python3-requirements.yaml`, so the build needs no
network access, as Flathub requires. On every pull request CI builds this manifest, launches the result
offscreen, checks that MP3, AAC, ALAC, FLAC, Vorbis and Opus actually decode inside the sandbox
(`decode_check.py`), and requires the Flathub linter to pass.

## Build locally
```sh
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak-builder --user --install --force-clean --install-deps-from=flathub build-dir \
  packaging/flatpak/io.github.phosphene_dev.Hallucinate.yml
flatpak run io.github.phosphene_dev.Hallucinate
```
Check the result with the same linter Flathub uses:
```sh
flatpak install --user flathub org.flatpak.Builder
flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest packaging/flatpak/io.github.phosphene_dev.Hallucinate.yml
```
To lint a built repo as well, build it the way CI does, with Flathub's builder mirroring the screenshots:
```sh
flatpak run org.flatpak.Builder --user --force-clean --install-deps-from=flathub \
  --mirror-screenshots-url=https://dl.flathub.org/media/ --repo=repo build-dir \
  packaging/flatpak/io.github.phosphene_dev.Hallucinate.yml
flatpak run --command=flatpak-builder-lint org.flatpak.Builder repo repo
```
Even then, `appstream-external-screenshot-url` and `appstream-remote-icon-not-mirrored` remain: only
Flathub's publishing pipeline rewrites media URLs to `dl.flathub.org/media`. CI excepts exactly those two
(`lint-exceptions.json`, passed with `--exceptions --user-exceptions`); any other error fails the build.

## Submitting to Flathub
Submission happens from your own GitHub account; see the
[Flathub submission guide](https://docs.flathub.org/docs/for-app-authors/submission).

1. Make sure the release you are submitting is tagged (for example `v0.3.2`) and that its
   `<release>` entry is in `io.github.phosphene_dev.Hallucinate.metainfo.xml`.
2. Fork [flathub/flathub](https://github.com/flathub/flathub) and create a branch from its
   `new-pr` branch.
3. Generate the submission files for the tag:
   ```sh
   git fetch --tags
   python scripts/flathub_manifest.py v0.8.0
   ```
   This writes `flathub-submission/io.github.phosphene_dev.Hallucinate.yml` (the manifest with its local
   source replaced by the tagged release and its full commit hash) and `python3-requirements.yaml`.
4. Copy both files into the root of your flathub/flathub branch.
5. Open a pull request against `new-pr` titled `Add io.github.phosphene_dev.Hallucinate`. Reviewers
   build it with `bot, build`. Expect questions about `--talk-name=org.freedesktop.Notifications` and the
   Discord socket, which are commented in the manifest.
6. After it is merged, Flathub creates `flathub/io.github.phosphene_dev.Hallucinate`; future releases
   are pull requests there that bump `tag`/`commit` (and `python3-requirements.yaml` when dependencies
   change).

The `io.github.phosphene_dev` app ID is verified through the GitHub account that owns this repository.

Inside the Flatpak, Hallucinate's own update check is off (Flathub delivers updates), and libraries of other
players are imported through the file chooser, since the sandbox can't look in their folders.

## Updating dependencies
`python3-requirements.yaml` explains how to regenerate it with
[flatpak-pip-generator](https://github.com/flatpak/flatpak-builder-tools/tree/master/pip). When moving to a
newer BaseApp, bump `runtime-version` and `base-version` together; they must match.
