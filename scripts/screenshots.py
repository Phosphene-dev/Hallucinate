"""Render README screenshots from a synthetic demo library.

    QT_QPA_PLATFORM=offscreen python scripts/screenshots.py docs/screenshots [--scale 2]

Needs PySide6, mutagen and numpy; ffmpeg is optional (tracks get audible tones with it, silent frames without).
The visualizer and Now Playing use GPU shaders, which Qt's offscreen software renderer can't draw (they fall
back to bars). For the real thing, render on an X server with OpenGL, e.g. headless with Mesa:

    Xvfb :77 -screen 0 1280x800x24 &
    DISPLAY=:77 QT_QPA_PLATFORM=xcb QSG_RHI_BACKEND=opengl python scripts/screenshots.py docs/screenshots

The visualizer is fed a made-up spectrum so the shots don't depend on an audio device.

With ffmpeg it also cross-fades a few of the shots into a looping tour: demo.mp4 for the website and demo.webp
for the README.
"""
import argparse
import os
import random
import sys
import tempfile
import time
from pathlib import Path

from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
from PySide6.QtCore import Q_ARG, QBuffer, QByteArray, QIODevice, QMetaObject, QPoint, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QImage, QLinearGradient, QPainter

GENRES = ["Dream Pop", "Indie Folk", "Synthwave", "Ambient", "Folk", "Chamber Jazz", "Indie Folk", "Post-Rock"]
YEARS = [2019, 2014, 1986, 2021, 2009, 1998, 2016, 2023]
ALBUMS = [
    ("Aurora Vale", "Northern Lights", ["Echoes of Dawn", "Midnight Rain", "Glass Horizon", "Polar Drift"]),
    ("Blue Harbor", "Tidal", ["Salt & Rope", "Lantern Bay", "Low Tide", "Harbor Lights"]),
    ("Cinder Fox", "Ember Season", ["Ash Road", "Slow Burn", "Foxfire", "Kindling"]),
    ("Daydream Atlas", "Cartography", ["Map of Silence", "Longitude", "Meridian", "Compass Rose"]),
    ("Echo Meadow", "Fieldwork", ["Clover", "Dew Point", "Hayloft", "Evening Grass"]),
    ("Fable Quartet", "Folio", ["Prologue", "Marginalia", "Colophon", "Epilogue"]),
    ("Glass Orchard", "Windfall", ["Cider", "Bough", "Orchard Rain", "Harvest Moon"]),
    ("Hollow Pines", "Evergreen", ["Needles", "Understory", "Timberline", "Frost"]),
]


def cover(seed):
    rnd = random.Random(seed)
    img = QImage(500, 500, QImage.Format.Format_RGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, 500, 500)
    g.setColorAt(0, QColor.fromHsv(rnd.randrange(360), 180, 220))
    g.setColorAt(1, QColor.fromHsv(rnd.randrange(360), 200, 120))
    p.fillRect(img.rect(), QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(5):
        p.setBrush(QColor.fromHsv(rnd.randrange(360), 120, 255, 70))
        p.drawEllipse(rnd.randrange(-100, 400), rnd.randrange(-100, 400), rnd.randrange(120, 400), rnd.randrange(120, 400))
    p.end()
    ba, buf = QByteArray(), None
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def _render_tone(path, seed, seconds):
    """Audible demo track with a varied loudness shape (so waveforms look real); needs ffmpeg."""
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return False
    rnd = random.Random(seed)
    f1, f2, slow, beat = rnd.choice([196, 220, 247, 262, 294]), rnd.choice([330, 392, 440]), rnd.uniform(9, 23), rnd.uniform(0.45, 0.9)
    expr = (f"(0.55*sin(2*PI*{f1}*t)+0.25*sin(2*PI*{f2}*t))"
            f"*(0.35+0.65*abs(sin(PI*t/{slow:.2f})))*(0.55+0.45*abs(sin(2*PI*t/{beat:.2f})))"
            f"*min(1,t/3)*min(1,({seconds}-t)/4)")
    result = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={seconds}",
         "-ac", "2", "-b:a", "192k", str(path)], capture_output=True)
    return result.returncode == 0


def build_library(root: Path):
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
    for n, (artist, album, tracks) in enumerate(ALBUMS):
        art = cover(n)
        d = root / artist / album
        d.mkdir(parents=True)
        for i, title in enumerate(tracks, 1):
            f = d / f"{i:02d} {title}.mp3"
            if not _render_tone(f, seed=n * 10 + i, seconds=40 + 9 * i):
                f.write_bytes(frame * (400 + 60 * i))
            t = ID3()
            t.add(TIT2(encoding=3, text=title))
            t.add(TPE1(encoding=3, text=artist))
            t.add(TPE2(encoding=3, text=artist))
            t.add(TALB(encoding=3, text=album))
            t.add(TRCK(encoding=3, text=f"{i}/{len(tracks)}"))
            t.add(TCON(encoding=3, text=GENRES[n]))
            t.add(TDRC(encoding=3, text=str(YEARS[n])))
            t.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=art))
            t.save(f)


# The tour, in order; it loops back to the first shot.
DEMO_SHOTS = ["home", "albums-colour", "album", "album-menu", "now-playing", "albums-timeline", "theme-trans-pride",
              "visualizer"]


def make_demo(out, names, hold=2.2, fade=0.6):
    """Cross-fade shots into a seamless loop: demo.mp4 (website, needs ffmpeg) and demo.webp (README, needs Pillow).

    The WebP is built from the screenshots themselves, not from the video: each held shot is one frame and only
    the fades add frames, so it can use a high quality. Re-encoding the video at low quality turned the dark
    backdrop into blocks."""
    import shutil
    import subprocess

    if shutil.which("ffmpeg"):
        files = [out / f"{n}.png" for n in names] + [out / f"{names[0]}.png"]
        inputs = []
        for f in files:
            inputs += ["-loop", "1", "-t", f"{hold + fade:.2f}", "-i", str(f)]
        chain, last = [], "0:v"
        for i in range(1, len(files)):
            label = f"v{i}"
            chain.append(f"[{last}][{i}:v]xfade=transition=fade:duration={fade}:offset={i * hold:.2f}[{label}]")
            last = label
        # the first shot comes back at the end: cut as soon as it has fully faded in, where the loop starts again
        total = (len(files) - 1) * hold + fade
        graph = ";".join(chain) + f";[{last}]trim=duration={total:.2f},fps=25,format=yuv420p[out]"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[out]",
                        "-c:v", "libx264", "-crf", "20", "-preset", "slow", "-tune", "stillimage",
                        "-movflags", "+faststart", str(out / "demo.mp4")], check=True)
        print("demo.mp4", f"{(out / 'demo.mp4').stat().st_size / 1e6:.1f} MB")
    else:
        print("ffmpeg not found; skipping demo.mp4")
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; skipping demo.webp")
        return
    shots = [Image.open(out / f"{n}.png").convert("RGB") for n in names]
    shots = [s.resize((860, round(s.height * 860 / s.width)), Image.LANCZOS) for s in shots]
    steps = 8
    frames, durations = [], []
    for i, a in enumerate(shots):
        b = shots[(i + 1) % len(shots)]
        frames.append(a)
        durations.append(round(hold * 1000))
        for k in range(1, steps):
            frames.append(Image.blend(a, b, k / steps))
            durations.append(round(fade * 1000 / steps))
    frames[0].save(out / "demo.webp", save_all=True, append_images=frames[1:], duration=durations, loop=0,
                   quality=90, method=6)
    print("demo.webp", f"{(out / 'demo.webp').stat().st_size / 1e6:.1f} MB")


def make_gif(out, frames, target):
    """Theme cross-section for the README (needs Pillow; skipped without it)."""
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; skipping", target.name)
        return
    images = [Image.open(out / f).convert("RGB").resize((800, 500), Image.LANCZOS) for f in frames]
    images[0].save(target, save_all=True, append_images=images[1:], duration=1400, loop=0, optimize=True)
    for f in frames:  # the GIF replaces the individual theme frames
        (out / f).unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--themes", default="Hallucinate,Dark,Light,Catppuccin Mocha,Nord")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="mp-shots-"))
    os.environ["HALLUCINATE_DATA"] = str(work / "data")
    os.environ["HALLUCINATE_DISABLE_LEGACY_MIGRATION"] = "1"
    os.environ["XDG_CONFIG_HOME"] = str(work / "config")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    build_library(work / "Music")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import hallucinate.app as appmod

    managers = []
    orig_tm = appmod.ThemeManager

    class TM(orig_tm):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            managers.append(self)

    appmod.ThemeManager = TM

    suffix = "" if args.scale == 1 else f"@{args.scale:g}x"
    base = appmod.QApplication

    class Shots(base):
        def exec(self):
            QTimer.singleShot(2500, lambda: self.run_shots())
            return super().exec()

        def run_shots(self):
            from PySide6.QtQml import QQmlEngine

            win = next(w for w in self.topLevelWindows() if w.title())
            win.resize(1280, 800)
            ctx = QQmlEngine.contextForObject(win)
            library, player, user_lib = (ctx.contextProperty(n) for n in ("library", "player", "userLib"))
            themes = [t.strip() for t in args.themes.split(",") if t.strip()]
            todo = []

            def shot(name):
                return lambda: win.grabWindow().save(str(out / f"{name}{suffix}.png"))

            def go(page):
                return lambda: QMetaObject.invokeMethod(win, "go", Q_ARG("QVariant", page))

            def seed():
                # A little listening history so Home, Stats and radio have something to show.
                tracks = library.allTracks()
                rnd = random.Random(7)
                now = time.time()
                when = [now - rnd.betavariate(1, 3) * 200 * 86400 for _ in range(260)]
                plays = [(rnd.choice(tracks)["path"], ts) for ts in when if rnd.random() < 0.85]
                plays += [(t["path"], now - rnd.uniform(60, 6 * 3600)) for t in rnd.sample(tracks, 6)]
                user_lib._reader.submit(lambda db: [db.record_play(p, ts) for p, ts in plays]).result()
                for t in rnd.sample(tracks, 8):
                    user_lib.toggleLike(t["path"])
                state["smart"] = user_lib.createSmartPlaylist("Late-night dreams", (
                    '{"match": "any", "rules": [{"field": "genre", "op": "contains", "value": "dream"},'
                    ' {"field": "genre", "op": "contains", "value": "ambient"}], "sort": "year_desc", "limit": 0}'))
                user_lib.refresh()
                user_lib.refreshStats()
                shell.setUiValue("foldersPath", str(work / "Music"))  # the folder view opens inside the music

            def play():
                player.setVisualizerEnabled(True)
                tracks = library.allTracks()
                player.setRadio(True)
                player.playList(tracks[4:6], 0)

            def pause():
                player.pause()
                player.seek(int(player.duration * 0.4))

            def open_smart():
                QMetaObject.invokeMethod(win, "openSmartPlaylist", Q_ARG("QVariant", state["smart"]),
                                         Q_ARG("QVariant", "Late-night dreams"))

            def editor(method, *values):
                def call():
                    from PySide6.QtCore import QObject
                    smart_editor = win.findChild(QObject, "smartEditor")
                    QMetaObject.invokeMethod(smart_editor, method,
                                             *[Q_ARG("QVariant", v() if callable(v) else v) for v in values])
                return call

            state = {}
            from PySide6.QtCore import QObject
            shell = ctx.contextProperty("shell")

            def child(name):
                return win.findChild(QObject, name)

            def fake_spectrum():
                # Deterministic, music-like levels: a pulsing low end and a slowly wandering mid and top.
                import math
                phase = state.setdefault("phase", [0.0])
                phase[0] += 0.07
                t = phase[0]
                levels = [max(0.0, min(1.0, (0.85 - i * 0.026) * (0.55 + 0.45 * math.sin(t * (1.3 + i * 0.21) + i))))
                          for i in range(24)]
                player._visualizer_levels = levels
                player.visualizerChanged.emit()

            timer = QTimer(self)
            timer.timeout.connect(fake_spectrum)
            timer.start(33)
            self._spectrum_timer = timer

            def albums_view(view):
                return lambda: shell.setUiValue("albumsView", view)

            def open_album():
                QMetaObject.invokeMethod(win, "openAlbum", Q_ARG("QVariant", library.albums.get(7)["album_key"]))

            def album_menu():
                a = library.albums.get(7)
                menu = child("albumMenu")
                QMetaObject.invokeMethod(menu, "show", Q_ARG("QVariant", [a["album_key"]]),
                                         Q_ARG("QVariant", a["album"]), Q_ARG("QVariant", a["album_artist"]))
                menu.setProperty("x", 560)
                menu.setProperty("y", 230)
                QCursor.setPos(win.mapToGlobal(QPoint(1200, 40)))  # keep the pointer off the menu
                menu.setProperty("currentIndex", 1)  # one row hovered

            def edit_album():
                QMetaObject.invokeMethod(child("tagEditor"), "editAlbum", Q_ARG("QVariant", library.albums.get(7)["album_key"]))

            def confirm_trash():
                a = library.albums.get(7)
                dlg = child("trashAlbumsDialog")
                dlg.setProperty("what", "“" + a["album"] + "”")
                dlg.open()

            def palette_query():
                QMetaObject.invokeMethod(child("commandPalette"), "show")
                child("paletteField").setProperty("text", "aur")
                library.search("aur")

            def palette_refresh():
                QMetaObject.invokeMethod(child("commandPalette"), "rebuild")

            def wait():
                return None

            def open_artist():
                QMetaObject.invokeMethod(win, "openArtist", Q_ARG("QVariant", "Glass Orchard"))

            def select_songs():
                # Ctrl+click one song and Shift+click a few rows down, as a user would
                from PySide6.QtCore import QPoint, Qt
                from PySide6.QtTest import QTest

                def rows(item, acc):
                    if item.isVisible():
                        if item.objectName() == "trackRow" and item.width() > 0:
                            acc.append(item)
                        for c in item.childItems():
                            rows(c, acc)
                    return acc

                found = rows(win.contentItem(), [])
                for row, mod in ((found[2], Qt.KeyboardModifier.ControlModifier),
                                 (found[5], Qt.KeyboardModifier.ShiftModifier)):
                    c = row.mapToScene(row.boundingRect().center())
                    QTest.mouseClick(win, Qt.MouseButton.LeftButton, mod, QPoint(int(c.x()), int(c.y())))

            def welcome(step):
                def show():
                    w = child("welcome")
                    w.setProperty("open", step >= 0)
                    w.setProperty("step", max(step, 0))
                return show

            todo += [seed, play, pause]
            for page in ("home", "songs", "history", "settings", "folders", "recap", "stats"):
                todo += [go(page), wait, shot(page)]
            todo += [go("artists"), open_artist, wait, shot("artist")]
            todo += [go("songs"), wait, select_songs, wait, shot("selection"), lambda: child("selectionClear").clicked.emit()]
            todo += [welcome(1), wait, shot("welcome-themes"), welcome(-1), wait]
            todo += [lambda: managers[0].selectTheme("Trans Pride"), go("home"), wait, wait, shot("theme-trans-pride"),
                     lambda: managers[0].selectTheme("Bi Pride"), wait, wait, shot("theme-bi-pride"),
                     lambda: managers[0].selectTheme(themes[0]), wait]
            for view in ("grid", "colour", "timeline"):
                todo += [albums_view(view), go("home"), go("albums"), wait, shot("albums" if view == "grid" else "albums-" + view)]
            todo += [albums_view("grid"), open_album, wait, shot("album")]
            todo += [album_menu, wait, shot("album-menu"), lambda: child("albumMenu").close(), wait]
            todo += [edit_album, wait, shot("edit-album"), lambda: child("tagEditor").reject(), wait]
            todo += [confirm_trash, wait, shot("confirm-trash"), lambda: child("trashAlbumsDialog").reject(), wait]
            todo += [lambda: shell.setVisualizerStyle("nebula"), go("visualizer"), wait, shot("visualizer")]
            todo += [lambda: shell.setVisualizerStyle("aurora"), lambda: child("nowPlayingView").setProperty("open", True),
                     wait, wait, shot("now-playing")]
            todo += [lambda: shell.setNowPlayingVinyl(True), lambda: shell.setVisualizerStyle("liquid"), wait, wait,
                     shot("now-playing-vinyl"), lambda: shell.setNowPlayingVinyl(False),
                     lambda: child("nowPlayingView").setProperty("open", False), wait]
            todo += [go("health"), wait, shot("health")]
            todo += [go("home"), palette_query, wait, palette_refresh, shot("palette"),
                     lambda: child("commandPalette").close(), wait]
            todo += [lambda: child("signalPathPopup").open(), shot("signal-path"), lambda: child("signalPathPopup").close()]
            todo += [lambda: win.setProperty("queueOpen", True), shot("queue"),
                     lambda: win.setProperty("queueOpen", False)]
            todo += [open_smart, shot("smart-playlist"),
                     editor("openEdit", lambda: state["smart"], "Late-night dreams")]
            todo += [shot("smart-editor"), editor("reject"), go("home")]
            for th in themes:
                slug = th.lower().replace(" ", "-")
                todo += [lambda t=th: managers[0].selectTheme(t), shot(f"theme-{slug}")]
            todo.append(lambda: managers[0].selectTheme(themes[0]))
            todo.append(lambda: player.setRadio(False))
            todo.append(lambda: make_gif(out, [f"theme-{t.lower().replace(' ', '-')}{suffix}.png" for t in themes],
                                         out / f"themes{suffix}.gif"))
            if not suffix:
                todo.append(lambda: make_demo(out, DEMO_SHOTS))

            def next_step():
                if todo:
                    todo.pop(0)()
                    QTimer.singleShot(900, next_step)
                else:
                    self.quit()

            next_step()

    appmod.QApplication = Shots
    sys.exit(appmod.main([str(work / "Music")]))


if __name__ == "__main__":
    main()
