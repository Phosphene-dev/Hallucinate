#!/usr/bin/env bash
# Unpack the newest published Flatpak repository (the flatpak-repo.tar attached to a release) into DIR.
#
#   packaging/flatpak/fetch_repo.sh DIR [SKIP_TAG]
#
# SKIP_TAG leaves out a release (the one being built). Prints the tag it used; prints nothing, and leaves DIR
# absent, when no release has a repository yet. Needs GH_TOKEN for the gh CLI.
set -euo pipefail

dir=$1 skip=${2:-}
for tag in $(gh release list --limit 30 --exclude-drafts --json tagName --jq '.[].tagName'); do
  [[ "$tag" == "$skip" ]] && continue
  if gh release view "$tag" --json assets --jq '.assets[].name' | grep -qx flatpak-repo.tar; then
    mkdir -p "$dir"
    gh release download "$tag" --pattern flatpak-repo.tar --output - | tar -x -C "$dir"
    echo "$tag"
    exit 0
  fi
done
