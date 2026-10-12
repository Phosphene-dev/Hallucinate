"""Write the dependency lists that CI checks for known vulnerabilities (pip-audit):

- deps.txt: the runtime dependencies from pyproject.toml, as a fresh install resolves them today;
- flatpak.txt: the exact versions pinned in the Flatpak's python3-requirements.yaml (wheel and sdist file names).

Usage: python scripts/audit_deps.py OUT_DIR"""
import re
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    (out / "deps.txt").write_text("\n".join(deps) + "\n")
    pins = {}
    yaml = (ROOT / "packaging" / "flatpak" / "python3-requirements.yaml").read_text()
    for name in re.findall(r"/([A-Za-z0-9_.]+?-\d[^/\s]*?)(?:-py\d|-cp\d|\.tar\.gz)", yaml):
        pkg, version = name.rsplit("-", 1)
        pins[pkg.lower().replace("_", "-")] = version
    (out / "flatpak.txt").write_text("".join(f"{p}=={v}\n" for p, v in sorted(pins.items())))
    print(f"{len(deps)} dependencies, {len(pins)} Flatpak pins")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "audit")
