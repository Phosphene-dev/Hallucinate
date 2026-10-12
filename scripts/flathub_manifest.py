"""Write the Flathub submission manifest for a release tag.

    python scripts/flathub_manifest.py v0.8.0 [out_dir]

Copies packaging/flatpak/io.github.phosphene_dev.Hallucinate.yml and python3-requirements.yaml to out_dir
(default: flathub-submission/), replacing the local `type: dir` source with the tagged release on GitHub and
its full commit hash. The result is what goes into a pull request to flathub/flathub's new-pr branch (see
packaging/flatpak/README.md)."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ID = "io.github.phosphene_dev.Hallucinate"
REPO = "https://github.com/Phosphene-dev/Hallucinate.git"


def main(argv):
    if not argv or not re.fullmatch(r"v\d+\.\d+\.\d+", argv[0]):
        print(__doc__)
        return 2
    tag = argv[0]
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "flathub-submission"
    try:
        commit = subprocess.run(["git", "rev-parse", f"{tag}^{{commit}}"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError:
        print(f"Tag {tag} not found; fetch tags first (git fetch --tags)", file=sys.stderr)
        return 1
    manifest = (ROOT / "packaging" / "flatpak" / f"{APP_ID}.yml").read_text(encoding="utf-8")
    source = re.compile(r"(?ms)^(?P<indent>\s*)sources:\n.*?- type: dir\n\s*path: \.\./\.\.\n")
    match = source.search(manifest)
    if not match:
        print("Couldn't find the local source in the manifest", file=sys.stderr)
        return 1
    indent = match.group("indent")
    replacement = (f"{indent}sources:\n{indent}  - type: git\n{indent}    url: {REPO}\n"
                   f"{indent}    tag: {tag}\n{indent}    commit: {commit}\n")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{APP_ID}.yml").write_text(manifest[:match.start()] + replacement + manifest[match.end():], encoding="utf-8")
    shutil.copy(ROOT / "packaging" / "flatpak" / "python3-requirements.yaml", out / "python3-requirements.yaml")
    print(f"Wrote {out}/{APP_ID}.yml for {tag} ({commit[:12]}) and python3-requirements.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
