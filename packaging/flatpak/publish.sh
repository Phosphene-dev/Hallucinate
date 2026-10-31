#!/usr/bin/env bash
# Sign a freshly built Flatpak repository and make the single-file bundle that points at it.
#
#   packaging/flatpak/publish.sh REPO KEY_ID GPG_HOMEDIR PUBLIC_KEY BUNDLE [ARM_BUNDLE]
#
# The repository can hold more than one processor's build (x86_64, and aarch64 copied in from its own runner):
# each is signed. BUNDLE is the x86_64 one; ARM_BUNDLE, when given, the aarch64 one.
#
# REPO is the OSTree repo flatpak-builder exported to (--repo=REPO --default-branch=stable). It may still hold the
# previous release (see fetch_repo.sh), which makes updates small: the new commit gets a delta from it, then
# anything older is pruned. KEY_ID signs the commit, the repo summary and the bundle; PUBLIC_KEY (binary
# `gpg --export` output) goes into the bundle, so installing it also adds the repository as a trusted remote.
set -euo pipefail

repo=$1 key=$2 home=$3 pubkey=$4 bundle=$5 arm_bundle=${6:-}
app=io.github.phosphene_dev.Hallucinate
branch=stable
url=https://phosphene-dev.github.io/Hallucinate/flatpak/repo/
sign=(--gpg-sign="$key" --gpg-homedir="$home")

for arch in x86_64 aarch64; do
  if ostree --repo="$repo" rev-parse "app/$app/$arch/$branch" >/dev/null 2>&1 \
     || [ -e "$repo/refs/heads/app/$app/$arch/$branch" ]; then
    flatpak build-sign --arch="$arch" "${sign[@]}" "$repo" "$app" "$branch"
  fi
done
# Keep one previous commit so the new one gets a delta from it; also writes the AppStream data that software
# centres read, and the signed summary.
flatpak build-update-repo "${sign[@]}" --title=Hallucinate --default-branch="$branch" \
  --generate-static-deltas --prune --prune-depth=1 "$repo"
flatpak build-bundle "${sign[@]}" --gpg-keys="$pubkey" --repo-url="$url" \
  --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
  "$repo" "$bundle" "$app" "$branch"
if [ -n "$arm_bundle" ]; then
  flatpak build-bundle --arch=aarch64 "${sign[@]}" --gpg-keys="$pubkey" --repo-url="$url" \
    --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    "$repo" "$arm_bundle" "$app" "$branch"
fi
du -sh "$repo" "$bundle" ${arm_bundle:+"$arm_bundle"}
