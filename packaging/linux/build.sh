#!/usr/bin/env bash
# Make the .deb and .rpm from an AppImage's AppDir (packaging/appimage/build.sh with KEEP_APPDIR=dir).
# Usage: packaging/linux/build.sh VERSION APPDIR [OUTDIR]  ->  hallucinate_VERSION_amd64.deb, hallucinate-VERSION-1.x86_64.rpm
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
version="$1"
appdir="$(realpath "$2")"
outdir="$(realpath -m "${3:-.}")"
mkdir -p "$outdir"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# A fixed release of nFPM, checked against its checksum
nfpm_version=2.43.0
nfpm_sha=a80d5f724ed70b192ffa8a2bde469c013cef559c8afa3441eb51dd9a918beb6b
curl -fsSL -o "$work/nfpm.tgz" \
  "https://github.com/goreleaser/nfpm/releases/download/v$nfpm_version/nfpm_${nfpm_version}_Linux_x86_64.tar.gz"
echo "$nfpm_sha  $work/nfpm.tgz" | sha256sum -c --quiet -
tar -xzf "$work/nfpm.tgz" -C "$work" nfpm

# The AppImage's desktop entry and icon at the AppDir's top are for appimagetool; the system's are installed apart
cp -a "$appdir" "$work/app"
rm -f "$work/app/hallucinate.desktop" "$work/app/hallucinate.png" "$work/app/.DirIcon"

for kind in deb rpm; do
  sed "s/system}\"/$kind}\"/" "$repo/packaging/linux/hallucinate" > "$work/hallucinate-$kind"
  # (nFPM expands variables only in a few fields: the paths are filled in here)
  sed -e "s#\${REPO}/packaging/linux/hallucinate\$#$work/hallucinate-$kind#" -e "s#\${REPO}#$repo#g" \
      -e "s#\${APPDIR}#$work/app#g" -e "s#\${VERSION}#$version#g" \
      "$repo/packaging/linux/nfpm.yaml" > "$work/nfpm-$kind.yaml"
  "$work/nfpm" package --config "$work/nfpm-$kind.yaml" --packager "$kind" --target "$outdir/"
done
ls -lh "$outdir"/hallucinate*"$version"*.{deb,rpm}
