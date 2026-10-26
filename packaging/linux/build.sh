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

# Every library the bundle links to and doesn't carry must be a dependency of the packages (nfpm.yaml's rpm list,
# by soname), or a clean system installs them without it. Optional plugins' libraries are left out.
optional='^(ld-linux-x86-64\.so\.2|lib(c|m|dl|rt|pthread|resolv|gcc_s)\.so\.[0-9]+|libQt6EglFsKmsGbmSupport\.so\.6|libgbm\.so\.1|libgtk-3\.so\.0|libgdk-3\.so\.0|libgdk_pixbuf-2\.0\.so\.0|libatk-1\.0\.so\.0|libcairo(-gobject)?\.so\.2|libpango(cairo)?-1\.0\.so\.0|libharfbuzz\.so\.0)$'
find "$work/app" -name '*.so*' -type f -exec objdump -p {} + 2>/dev/null | awk '/NEEDED/{print $2}' | sort -u > "$work/needed"
find "$work/app" -name '*.so*' -printf '%f\n' | sort -u > "$work/carried"
missing="$(comm -23 "$work/needed" "$work/carried" | grep -Ev "$optional" | while read -r so; do
  grep -qF -- "- $so()(64bit)" "$repo/packaging/linux/nfpm.yaml" || echo "$so"; done)"
if [ -n "$missing" ]; then
  echo "Libraries the bundle needs that the packages don't depend on (add them to packaging/linux/nfpm.yaml):" >&2
  echo "$missing" >&2
  exit 1
fi

for kind in deb rpm; do
  sed "s/system}\"/$kind}\"/" "$repo/packaging/linux/hallucinate" > "$work/hallucinate-$kind"
  # (nFPM expands variables only in a few fields: the paths are filled in here)
  sed -e "s#\${REPO}/packaging/linux/hallucinate\$#$work/hallucinate-$kind#" -e "s#\${REPO}#$repo#g" \
      -e "s#\${APPDIR}#$work/app#g" -e "s#\${VERSION}#$version#g" \
      "$repo/packaging/linux/nfpm.yaml" > "$work/nfpm-$kind.yaml"
  "$work/nfpm" package --config "$work/nfpm-$kind.yaml" --packager "$kind" --target "$outdir/"
done
ls -lh "$outdir"/hallucinate*"$version"*.{deb,rpm}
