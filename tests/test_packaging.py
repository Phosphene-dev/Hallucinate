"""The packaged builds: which parts of Qt they leave out (packaging/qt_prune.py) and the decode check they run."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

import qt_prune  # noqa: E402

REMOVED = [
    "PySide6/Qt/lib/libQt6WebEngineCore.so.6", "PySide6/Qt6WebEngineCore.dll", "PySide6/QtWebEngineCore.pyd",
    "PySide6/Qt/lib/QtWebEngineCore.framework", "PySide6/Qt/libexec/QtWebEngineProcess",
    "PySide6/Qt/resources/icudtl.dat", "PySide6/Qt/resources/qtwebengine_resources.pak",
    "PySide6/Qt/translations/qtwebengine_locales", "PySide6/Qt/translations/qtwebengine_de.qm",
    "PySide6/Qt/lib/libQt63DQuickRender.so.6", "PySide6/Qt/lib/libQt6Quick3DPhysics.so.6",
    "PySide6/Qt/lib/libQt6PdfQuick.so.6", "PySide6/Qt/lib/libQt6QuickControls2MaterialStyleImpl.so.6",
    "PySide6/Qt/qml/QtQuick/Controls/Material", "PySide6/Qt/qml/QtQuick3D", "PySide6/Qt/qml/QtQuick/Particles",
    "PySide6/Qt/plugins/sqldrivers", "PySide6/Qt/plugins/imageformats/libqpdf.so",
    "PySide6/Qt/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    "PySide6/designer", "PySide6/qmlls", "PySide6/QtCore.pyi", "PySide6/include", "PySide6/Qt/metatypes",
]
KEPT = [
    "PySide6/Qt/lib/libQt6Core.so.6", "PySide6/Qt/lib/libQt6Quick.so.6", "PySide6/Qt/lib/libQt6Multimedia.so.6",
    "PySide6/Qt/lib/libQt6Concurrent.so.6", "PySide6/Qt/lib/libQt6ShaderTools.so.6",
    "PySide6/Qt/lib/libQt6QuickControls2Basic.so.6", "PySide6/Qt/lib/libQt6QuickEffects.so.6",
    "PySide6/Qt/lib/libQt6QuickDialogs2QuickImpl.so.6", "PySide6/Qt/lib/libQt6WaylandClient.so.6",
    "PySide6/Qt/lib/libQt6DBus.so.6", "PySide6/Qt/lib/libQt6Network.so.6", "PySide6/Qt/lib/libavcodec.so.63",
    "PySide6/Qt/lib/libicudata.so.73", "PySide6/opengl32sw.dll",
    "PySide6/Qt/qml/QtQuick/Controls/Basic", "PySide6/Qt/qml/QtQuick/Effects", "PySide6/Qt/qml/QtQuick/Dialogs",
    "PySide6/Qt/qml/QtQuick/Shapes", "PySide6/Qt/plugins/multimedia", "PySide6/Qt/plugins/platforms",
    "PySide6/Qt/plugins/wayland-shell-integration", "PySide6/Qt/plugins/tls",
    "PySide6/Qt/translations/qtbase_de.qm", "PySide6/QtMultimedia.abi3.so", "PySide6/QtQuick.pyd",
    # nothing outside PySide6 is ever touched, whatever its name
    "hallucinate/qml/Timeline.qml", "numpy/include", "python3.12/test", "scripts",
]


def test_prune_rules():
    assert [p for p in REMOVED if not qt_prune.unused(p)] == []
    assert [p for p in KEPT if qt_prune.unused(p)] == []


def test_prune_removes_folders_files_and_dangling_links(tmp_path):
    root = tmp_path / "Hallucinate"
    for rel in ["_internal/PySide6/Qt6WebEngineCore.dll", "_internal/PySide6/Qt6Core.dll",
                "_internal/PySide6/qml/QtQuick3D/qmldir", "_internal/PySide6/qml/QtQuick/Controls/Basic/qmldir"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"x" * 10)
    if os.name != "nt":
        (root / "_internal/PySide6/link").symlink_to(root / "_internal/PySide6/Qt6WebEngineCore.dll")
    count, size = qt_prune.prune(root)
    left = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    assert left == ["_internal/PySide6/Qt6Core.dll", "_internal/PySide6/qml/QtQuick/Controls/Basic/qmldir"]
    assert count >= 2 and size >= 20
    assert not (root / "_internal/PySide6/link").is_symlink()


def test_decode_check_plays_every_format():
    clips = sorted(str(p) for p in (ROOT / "packaging" / "testclips").iterdir())
    assert len(clips) == 7
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-m", "hallucinate", "--decode-check", *clips],
                       capture_output=True, text=True, timeout=120, env=env, cwd=ROOT)
    if "ImportError" in r.stderr and "PySide6" in r.stderr:
        pytest.skip("PySide6 is not usable in this environment")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("ok  ") == 8, r.stdout  # seven clips, and the analysis helper


def test_decode_check_fails_on_a_file_that_does_not_play(tmp_path):
    bad = tmp_path / "not-audio.mp3"
    bad.write_bytes(b"\0" * 4096)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-m", "hallucinate", "--decode-check", str(bad)],
                       capture_output=True, text=True, timeout=120, env=env, cwd=ROOT)
    assert r.returncode == 1 and "FAIL" in r.stdout


def test_every_package_is_listed_for_installing():
    """pyproject lists the packages by hand: one left out installs without it, and the installed app fails to start
    (the source tree, where the tests run, has it either way)."""
    from pathlib import Path

    tomllib = pytest.importorskip("tomllib")  # (Python 3.11+)
    root = Path(__file__).resolve().parents[1]
    listed = set(tomllib.loads((root / "pyproject.toml").read_text())["tool"]["setuptools"]["packages"])
    found = {".".join(p.parent.relative_to(root).parts) for p in (root / "hallucinate").rglob("__init__.py")
             if "__pycache__" not in p.parts}
    assert found <= listed, sorted(found - listed)
