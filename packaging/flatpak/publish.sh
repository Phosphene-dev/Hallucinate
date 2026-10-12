#!/usr/bin/env bash
# Sign a freshly built Flatpak repository and make the single-file bundle that points at it.
#
#   packaging/flatpak/publish.sh REPO KEY_ID GPG_HOMEDIR PUBLIC_KEY BUNDLE
#
# REPO is the OSTree repo flatpak-builder exported to (--repo=REPO --default-branch=stable). It may still hold the
# previous release (see fetch_repo.sh), which makes updates small: the new commit gets a delta from it, then
# anything older is pruned. KEY_ID signs the commit, the repo summary and the bundle; PUBLIC_KEY (binary
# `gpg --export` output) goes into the bundle, so installing it also adds the repository as a trusted remote.
set -euo pipefail

repo=$1 key=$2 home=$3 pubkey=$4 bundle=$5
app=io.github.phosphene_dev.Hallucinate
branch=stable
url=https://phosphene-dev.github.io/Hallucinate/flatpak/repo/
sign=(--gpg-sign="$key" --gpg-homedir="$home")

flatpak build-sign "${sign[@]}" "$repo" "$app" "$branch"
# Keep one previous commit so the new one gets a delta from it; also writes the AppStream data that software
# centres read, and the signed summary.
flatpak build-update-repo "${sign[@]}" --title=Hallucinate --default-branch="$branch" \
  --generate-static-deltas --prune --prune-depth=1 "$repo"
flatpak build-bundle "${sign[@]}" --gpg-keys="$pubkey" --repo-url="$url" \
  --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
  "$repo" "$bundle" "$app" "$branch"
du -sh "$repo" "$bundle"
