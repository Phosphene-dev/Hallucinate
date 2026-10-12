# Flatpak

`io.github.phosphene_dev.Hallucinate.yml` builds Hallucinate on the KDE 6.11 runtime with the
[PySide BaseApp](https://github.com/flathub/io.qt.PySide.BaseApp) (PySide6 and numpy). The remaining
Python dependencies are pinned with checksums in `python3-requirements.yaml`, so the build needs no network
access. On every pull request CI builds this manifest, checks it with Flathub's linter, signs and publishes it
the way a release does (with a throwaway key), installs the resulting bundle, launches it offscreen and checks
that MP3, AAC, ALAC, FLAC, Vorbis and Opus actually decode inside the sandbox (`decode_check.py`).

Hallucinate isn't on Flathub. It has its own Flatpak repository instead, served from the website, so it
installs and updates like any other Flatpak app (software centres, `flatpak update`). The runtime still comes
from Flathub.

## Installing (what users do)
```sh
flatpak install --user https://phosphene-dev.github.io/Hallucinate/hallucinate.flatpakref
```
or open that link in GNOME Software or KDE Discover. Either adds the `hallucinate` remote (signed with the
project's key, `hallucinate-repo.gpg`) and Flathub for the runtime. Each release also has a single-file
`hallucinate-<version>-x86_64.flatpak` bundle; installing it (`flatpak install --user ./hallucinate-….flatpak`)
sets up the same remote, so it updates too.

## How releases publish it
The `flatpak` job in `.github/workflows/release.yml`:

1. downloads the previous release's repository (`flatpak-repo.tar`, via `fetch_repo.sh`);
2. builds the tagged source into it on the `stable` branch, so the new version has the old one as its parent;
3. signs it with `publish.sh`, which also writes a delta from the previous version (small updates), prunes
   anything older, and makes the bundle;
4. installs the bundle and launches it offscreen;
5. attaches the bundle and the new `flatpak-repo.tar` to the release.

The website build (`.github/workflows/pages.yml`, `scripts/build_site.py`) then serves the newest repository at
`/flatpak/repo/`, with `hallucinate.flatpakref` and `flatpak/hallucinate.flatpakrepo`, and offers it in the
download section. The repository holds two versions at most, which keeps the site well inside GitHub Pages'
1 GB limit.

## The signing key (one-time setup, by the maintainer)
Users' Flatpak checks every update against the public key they got when they installed, so the private key
must stay secret and must not be lost: replacing it means every user has to re-add the repository. Make it
on your own computer:

```sh
gpg --quick-gen-key "Hallucinate Flatpak repository" rsa4096 sign never   # leave the passphrase empty
KEY=$(gpg --with-colons --list-secret-keys "Hallucinate Flatpak repository" | awk -F: '$1 == "fpr" {print $10; exit}')
gpg --export "$KEY" > packaging/flatpak/hallucinate-repo.gpg                 # public: commit this
gpg --export-secret-keys --armor "$KEY" > hallucinate-repo-private.asc       # private: never commit this
```

1. Add the contents of `hallucinate-repo-private.asc` as a repository secret named `FLATPAK_GPG_PRIVATE_KEY`
   (Settings → Secrets and variables → Actions → New repository secret). An empty passphrase is fine there:
   the secret store protects it, and CI can't type one in.
2. Commit `packaging/flatpak/hallucinate-repo.gpg`.
3. Keep a backup of `hallucinate-repo-private.asc` somewhere safe and offline (a password manager works),
   then delete the loose copy.

Until both the secret and the public key are in place, releases skip the Flatpak repository and say so; the
other downloads are unaffected. The release job also checks that the secret matches the committed public key.

## Build locally
```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.flatpak.Builder
flatpak run org.flatpak.Builder --user --install --force-clean --install-deps-from=flathub build-dir \
  packaging/flatpak/io.github.phosphene_dev.Hallucinate.yml
flatpak run io.github.phosphene_dev.Hallucinate
```
Check it with Flathub's linter, as CI does:
```sh
flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest packaging/flatpak/io.github.phosphene_dev.Hallucinate.yml
```
`lint-exceptions.json` excepts the two repository checks that are about how Flathub's own servers rewrite
screenshot and icon URLs, which don't apply to this repository.

Inside the Flatpak, Hallucinate's own update check is off (the repository delivers updates), and libraries of
other players are imported through the file chooser, since the sandbox can't look in their folders.

## Updating dependencies
`python3-requirements.yaml` explains how to regenerate it with
[flatpak-pip-generator](https://github.com/flatpak/flatpak-builder-tools/tree/master/pip). When moving to a
newer BaseApp, bump `runtime-version` and `base-version` together; they must match.
