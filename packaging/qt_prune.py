"""Remove the parts of PySide6 that Hallucinate never uses from a built bundle.

    python packaging/qt_prune.py <bundle dir> [--dry-run]

The PySide6 wheels carry all of Qt: a web browser engine (about 200 MB on its own), 3D, charts, maps, PDF,
Bluetooth, the developer tools and more. The AppImage, the Windows build and the macOS app run this on their
output, so downloads (and in-app updates) carry only what the player needs. It removes whole modules only,
never part of one, and every build is launched and plays audio in CI afterwards (see the release workflow).

Kept: Core, Gui, Widgets, Network, Qml, Quick (with Controls' Basic style and the native ones, Templates,
Layouts, Shapes, Effects, Dialogs), Multimedia with its FFmpeg backend, DBus, OpenGL, the platform, Wayland
client, input-method, image-format and TLS plugins, and Qt's own translations for its dialogs.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

# Qt modules (libraries, frameworks, Python bindings, QML modules, translations) the app doesn't use.
MODULES = [
    "WebEngine", "WebChannel", "WebView", "WebSockets",
    "3DCore", "3DRender", "3DInput", "3DLogic", "3DExtras", "3DAnimation", "3DQuick", "Scene2D", "Scene3D",
    "Quick3D", "Pdf", "Charts", "DataVisualization", "Graphs", "Location", "Positioning", "Sensors",
    "Bluetooth", "Nfc", "TextToSpeech", "Designer", "UiTools", "Help", "HttpServer", "RemoteObjects",
    "Scxml", "StateMachine", "SerialPort", "SerialBus", "VirtualKeyboard", "SpatialAudio", "LabsStyleKit",
    "CanvasPainter", "NetworkAuth", "Test", "QuickTest", "Sql", "MultimediaWidgets",
    "OpenGLWidgets", "QmlLS", "QmlCompiler", "QmlDom", "QmlLint", "QmlFormat", "QmlToolingSettings",
    "LanguageServer", "JsonRpc", "Xml", "PrintSupport", "Asyncio", "QmlLocalStorage", "WaylandCompositor",
    "WaylandEglCompositor", "QuickControls2Material", "QuickControls2Universal", "QuickControls2Imagine",
    "QuickControls2FluentWinUI3", "Lottie", "QuickTimeline", "QuickParticles", "QmlDesignSupport",
    "QuickShapesDesignHelpers", "LabsWavefrontMesh",
]
# QtQuick Controls styles other than Basic (which HallucinateStyle builds on) and the platform-native ones.
STYLES = ["Material", "Universal", "Imagine", "FluentWinUI3"]
# Plugin folders for the removed modules (and the Wayland compositor side, which a client never loads).
PLUGIN_DIRS = [
    "assetimporters", "canbus", "designer", "geometryloaders", "geoservices", "position", "qmltooling",
    "renderers", "renderplugins", "sceneparsers", "scxmldatamodel", "sensors", "sqldrivers", "texttospeech",
    "webview", "wayland-graphics-integration-server", "qmllint", "qmlls", "printsupport",
]
# PySide's developer tools and build-time files.
TOOLS = ["assistant", "balsam", "balsamui", "designer", "linguist", "lrelease", "lupdate", "qmlformat",
         "qmllint", "qmlls", "qsb", "svgtoqml", "qmlcachegen", "qmlimportscanner", "qmltyperegistrar", "rcc",
         "uic", "QtWebEngineProcess", "pyside6-project", "Assistant.app", "Designer.app", "Linguist.app"]
DEV_DIRS = ["include", "typesystems", "glue", "scripts", "metatypes", "examples", "doc", "qtwebengine_locales"]
QML_MODULES = ["Qt3D", "QtQuick3D", "QtCharts", "QtDataVisualization", "QtGraphs", "QtLocation", "QtPositioning",
               "QtSensors", "QtTextToSpeech", "QtWebEngine", "QtWebChannel", "QtWebView", "QtWebSockets", "QtTest",
               "QtRemoteObjects", "QtScxml", "QtVirtualKeyboard", "QtSpatialAudio", "LocalStorage",
               "VirtualKeyboard", "Scene3D", "Scene2D", "Compositor", "Pdf", "StyleKit", "StateMachine",
               "Particles", "Timeline", "Lottie", "WavefrontMesh", "wavefrontmesh", "DesignSupport",
               "DesignHelpers"]
WEB_ENGINE_FILES = ["icudtl.dat", "v8_context_snapshot.bin"]
# Plugins of removed modules that sit in folders the app does use.
PLUGIN_FILES = re.compile(r"^(lib)?(qpdf|qtvirtualkeyboardplugin|qlottievectorimage)\.(so|dll|dylib)$")

# A module's name, and the libraries named after it (Qt63DQuickRender belongs to 3D, QtPdfQuick to Pdf).
_module = re.compile(r"^(?:lib)?Qt6?(?:%s)" % "|".join(re.escape(m) for m in MODULES))
_translation = re.compile(r"^(assistant|designer|linguist|qtconnectivity|qtlocation|qtserialport|qtwebengine|qtwebsockets)"
                          r"_.*\.qm$")


def unused(path):
    """Whether `path` (a file or folder inside a bundle) belongs to something the app never uses. Only
    PySide6's own files are ever matched."""
    path = Path(path)
    parts = path.parts
    if "PySide6" not in parts[:-1]:
        return False
    name = path.name
    parent = parts[-2]
    return bool(
        _module.search(name) or _translation.match(name) or PLUGIN_FILES.match(name)
        or name in WEB_ENGINE_FILES or name.startswith("qtwebengine")
        or name in DEV_DIRS or name in TOOLS or name.endswith(".pyi")
        or (parent == "plugins" and name in PLUGIN_DIRS)
        or (parent == "Controls" and name in STYLES)
        or name in QML_MODULES
    )


def prune(root, dry_run=False):
    """Remove the unused parts under `root`; returns (count, bytes) removed."""
    root = Path(root)
    removed, size = 0, 0
    # Walk top-down so a removed folder isn't descended into.
    stack = [root]
    while stack:
        folder = stack.pop()
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if unused(entry.relative_to(root.parent)):
                if entry.is_dir() and not entry.is_symlink():
                    size += sum(f.stat().st_size for f in entry.rglob("*") if f.is_file() and not f.is_symlink())
                    if not dry_run:
                        shutil.rmtree(entry)
                else:
                    size += entry.lstat().st_size
                    if not dry_run:
                        entry.unlink()
                removed += 1
            elif entry.is_dir() and not entry.is_symlink():
                stack.append(entry)
    if not dry_run:  # macOS bundles link Resources and Frameworks to each other; drop links to what's gone
        for link in [p for p in root.rglob("*") if p.is_symlink() and not p.exists()]:
            link.unlink()
    return removed, size


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", help="the bundle folder (AppDir, dist/Hallucinate or Hallucinate.app)")
    ap.add_argument("--dry-run", action="store_true", help="only list the total")
    args = ap.parse_args(argv)
    count, size = prune(args.root, args.dry_run)
    print(f"{'Would remove' if args.dry_run else 'Removed'} {count} unused Qt parts, {size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
