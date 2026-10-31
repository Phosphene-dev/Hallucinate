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

from mutagen.id3 import APIC, ID3, MVIN, MVNM, TALB, TBPM, TCOM, TCON, TDRC, TIT2, TKEY, TPE1, TPE2, TRCK, TXXX
from PySide6.QtCore import Q_ARG, QBuffer, QByteArray, QIODevice, QMetaObject, QPoint, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QImage, QLinearGradient, QPainter

GENRES = ["Dream Pop", "Indie Folk", "Synthwave", "Ambient", "Folk", "Chamber Jazz", "Indie Folk", "Post-Rock",
          "Classical"]
YEARS = [2019, 2014, 1986, 2021, 2009, 1998, 2016, 2023, 2018]
ALBUMS = [
    ("Aurora Vale", "Northern Lights", ["Echoes of Dawn", "Midnight Rain", "Glass Horizon", "Polar Drift"]),
    ("Blue Harbor", "Tidal", ["Salt & Rope", "Lantern Bay", "Low Tide", "Harbor Lights"]),
    ("Cinder Fox", "Ember Season", ["Ash Road", "Slow Burn", "Foxfire", "Kindling"]),
    ("Daydream Atlas", "Cartography", ["Map of Silence", "Longitude", "Meridian", "Compass Rose"]),
    ("Echo Meadow", "Fieldwork", ["Clover", "Dew Point", "Hayloft", "Evening Grass"]),
    ("Fable Quartet", "Folio", ["Prologue", "Marginalia", "Colophon", "Epilogue"]),
    ("Glass Orchard", "Windfall", ["Cider", "Bough", "Orchard Rain", "Harvest Moon"]),
    ("Hollow Pines", "Evergreen", ["Needles", "Understory", "Timberline", "Frost"]),
    ("Lumen Ensemble", "Nocturnes for Strings", ["Lento", "Andante cantabile", "Scherzo", "Adagio", "Allegro con fuoco"]),
]
# A made-up composer for the classical album: the composer page shows the work with its movements in order
COMPOSER, WORK = "Ilse Marten", "Nocturnes for Strings, Op. 3"
KEYS = ["Am", "C", "F#m", "Eb", "G", "Dm", "Bb", "E"]
# Made-up words for the lyrics view, a few long enough to wrap
LYRICS = ["Under a sky the colour of the sea", "we left the lights on for the morning",
          "and every street we never walked down was calling out our names, the long way home",
          "Glass horizon", "hold on, hold on", "the night is softer than it seems from here, so stay a little longer",
          "Under a sky the colour of the sea", ""]


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
            if artist == "Lumen Ensemble":
                t.add(TCOM(encoding=3, text=COMPOSER))
                t.add(TXXX(encoding=3, desc="WORK", text=WORK))
                t.add(MVNM(encoding=3, text=title))
                t.add(MVIN(encoding=3, text=f"{i}/{len(tracks)}"))
            else:  # tempo and key, for sorting Songs by tempo
                t.add(TBPM(encoding=3, text=str(70 + (n * 17 + i * 11) % 90)))
                t.add(TKEY(encoding=3, text=KEYS[(n + i) % len(KEYS)]))
            if artist == "Fable Quartet":  # a band that writes its own: a second composer
                t.add(TCOM(encoding=3, text="Mira Fable"))
            t.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=art))
            t.save(f)
            f.with_suffix(".lrc").write_text("".join(f"[00:{4 * k:02d}.00]{line}\n" for k, line in enumerate(LYRICS)))


# The tour, in order; it loops back to the first shot.
DEMO_SHOTS = ["home", "albums-colour", "album", "composer", "now-playing", "albums-timeline", "theme-trans-pride",
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
            todo = [lambda: managers[0].selectTheme(themes[0])]  # every shot in the first theme asked for

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
                # playlists, two of them in a folder (the sidebar shows it)
                rnd2 = random.Random(3)
                for name, folder in (("Morning run", "Workout"), ("Cool down", "Workout"), ("Rainy Sunday", "")):
                    pid = user_lib.createPlaylist(name)
                    user_lib.addPathsToPlaylist(pid, [t["path"] for t in rnd2.sample(tracks, 8)])
                    if folder:
                        user_lib.setPlaylistFolder(pid, False, folder)
                shell.setUiValue("playlistFolderOpen/Workout", "1")
                # similar artists as Last.fm would list them (stored, so nothing is asked)
                import json as _json

                sources = ctx.contextProperty("sources")
                sources._lastfm_key = lambda: "demo"
                sources.setFetchSimilar(True)
                similar = ctx.contextProperty("similarArtists")
                names = [{"name": n, "match": 1 - k / 10} for k, n in enumerate(
                    ["Hollow Pines", "Echo Meadow", "Aurora Vale", "Paper Lanterns", "The Quiet Fields", "Moth Radio",
                     "Saltwater Choir", "Kite Season"])]
                similar._db.conn.execute("INSERT OR REPLACE INTO similar_artists(s_aa, names, fetched) VALUES(?, ?, ?)",
                                         ("glass orchard", _json.dumps(names), time.time()))
                similar._db.conn.commit()
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

            def windfall():
                return next(library.albums.get(i) for i in range(library.albums.count)
                            if library.albums.get(i)["album"] == "Windfall")

            def albums_view(view):
                return lambda: shell.setUiValue("albumsView", view)

            def open_album():
                QMetaObject.invokeMethod(win, "openAlbum", Q_ARG("QVariant", windfall()["album_key"]))

            def mark_badges():
                # an explicit, hi-res album, so its badges show (the demo files are MP3s)
                key = windfall()["album_key"]
                user_lib._reader.submit(lambda db: (db.conn.execute(
                    "UPDATE tracks SET explicit=(track_no % 2), bit_depth=24, sample_rate=96000 WHERE album_key=?",
                    (key,)), db.commit())).result()
                library.reload()

            def open_volume():  # the narrow player bar's volume button opens its slider above it
                win.resize(700, 800)
                QTimer.singleShot(400, lambda: child("muteButton").findChild(QObject, "volumePopup").open())

            def close_volume():
                child("muteButton").findChild(QObject, "volumePopup").close()
                win.resize(1280, 800)

            def mini_shot(name):
                def grab():
                    mini = next(w for w in self.topLevelWindows() if w.title().endswith("Mini"))
                    mini.grabWindow().save(str(out / f"{name}{suffix}.png"))
                return grab

            def album_menu():
                a = windfall()
                menu = child("albumMenu")
                QMetaObject.invokeMethod(menu, "show", Q_ARG("QVariant", [a["album_key"]]),
                                         Q_ARG("QVariant", a["album"]), Q_ARG("QVariant", a["album_artist"]))
                menu.setProperty("x", 560)
                menu.setProperty("y", 230)
                QCursor.setPos(win.mapToGlobal(QPoint(1200, 40)))  # keep the pointer off the menu
                menu.setProperty("currentIndex", 1)  # one row hovered

            def edit_album():
                QMetaObject.invokeMethod(child("tagEditor"), "editAlbum", Q_ARG("QVariant", windfall()["album_key"]))

            def confirm_trash():
                a = windfall()
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

            def listening():
                # A few stations and shows, made up and with local art, so nothing is fetched.
                from hallucinate.core import net
                net.set_offline(True)  # the feeds are made up; don't try them
                stations, podcasts = ctx.contextProperty("stations"), ctx.contextProperty("podcasts")
                for i, (name, tags, country) in enumerate([
                        ("Night Owl FM", "ambient, chill", "Iceland"), ("Harbour Jazz", "jazz, swing", "Portugal"),
                        ("Static Bloom", "dream pop, shoegaze", "Japan"), ("Lowland Folk Radio", "folk, acoustic", "Ireland"),
                        ("Pulse 86", "synthwave, retro", "Canada")]):
                    favicon = f"https://example.invalid/{i}.png"
                    stations._db.add_station({"name": name, "url": f"http://127.0.0.1:9/{i}", "tags": tags,
                                              "country": country, "codec": "MP3", "bitrate": 128 + 64 * (i % 3),
                                              "favicon": favicon})
                    icon = stations._icon_file({"favicon": favicon})
                    icon.parent.mkdir(parents=True, exist_ok=True)
                    icon.write_bytes(cover(100 + i))
                stations.refresh()
                first_station = stations._db.stations()[0]
                now = time.time()
                heard = [("Aurora Vale", "Glass Horizon"), ("Daydream Atlas", "Meridian"), ("Echo Meadow", "Dew Point"),
                         ("Hollow Pines", "Timberline"), ("Glass Orchard", "Harvest Moon"), ("Fable Quartet", "Colophon")]
                for i, (artist, title) in enumerate(heard):
                    stations._db.log_radio_song(first_station["id"], first_station["name"], artist, title,
                                                ts=now - i * 1900 - 600)
                stations._db.add_listen_time("station", first_station["id"], first_station["name"], 3 * 3600 + 900)
                stations.logChanged.emit()
                art = work / "podcast-art"
                art.mkdir(exist_ok=True)
                now = time.time()
                shows = [("The Long Listen", "Mara Quill", ["Why albums still matter", "A history of the B-side",
                                                             "Inside a mastering studio", "The loudness war, revisited"]),
                         ("Field Notes", "Owen Hart", ["Recording birdsong at dawn", "The sound of snow", "Rivers"]),
                         ("Late Shift", "Ada & June", ["Night buses", "Diners after midnight", "Insomnia playlists"]),
                         ("Slow Science", "Dr. Ines Ruiz", ["How ears hear", "Why some chords feel sad"])]
                first = None
                for n, (title, author, eps) in enumerate(shows):
                    image = art / f"{n}.png"
                    image.write_bytes(cover(200 + n))
                    pid = podcasts._db.add_podcast({"title": title, "author": author, "feed_url": f"https://example.invalid/{n}",
                                                    "image": str(image),
                                                    "description": f"{title}, a show about listening closely."})
                    first = first or pid
                    podcasts._db.merge_episodes(pid, [
                        {"guid": f"{n}-{i}", "title": t, "url": f"https://example.invalid/{n}/{i}.mp3",
                         "published": now - (i * 7 + n) * 86400, "duration": 1800 + 600 * i,
                         "description": "What this episode covers, and who's in it."}
                        for i, t in enumerate(eps)])
                eps = podcasts._db.episodes(first)
                podcasts._db.set_position(eps[0]["id"], 1300)
                podcasts._db.set_played([eps[-1]["id"]], True)
                second = podcasts._db.episodes(first + 1)
                podcasts._db.set_up_next(second[0]["id"], True, False)
                podcasts._db.set_up_next(eps[1]["id"], True, False)
                podcasts.reload()
                state["show"] = first
                shell.setFeature("stations", True)
                shell.setFeature("podcasts", True)

            todo += [seed, listening, play, pause]
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
            todo += [lambda: child("createPlaylistDialog").open(), wait, shot("new-playlist"),
                     lambda: child("createPlaylistDialog").close(), wait]
            todo += [album_menu, wait, shot("album-menu"), lambda: child("albumMenu").close(), wait]
            todo += [edit_album, wait, shot("edit-album"), lambda: child("tagEditor").reject(), wait]
            todo += [confirm_trash, wait, shot("confirm-trash"), lambda: child("trashAlbumsDialog").reject(), wait]
            todo += [lambda: shell.setVisualizerStyle("nebula"), go("visualizer"), wait, shot("visualizer")]
            todo += [lambda: shell.setVisualizerStyle("aurora"), lambda: child("nowPlayingView").setProperty("open", True),
                     wait, wait, shot("now-playing"),
                     lambda: child("nowPlayingView").setProperty("lyricsMode", True), wait, wait, wait,
                     shot("now-playing-lyrics"), lambda: child("nowPlayingView").setProperty("lyricsMode", False),
                     lambda: child("nowPlayingView").setProperty("open", False), go("home"),
                     lambda: win.setProperty("lyricsOpen", True), wait, wait, shot("lyrics-panel"),
                     lambda: win.setProperty("lyricsOpen", False), wait]
            todo += [lambda: shell.setNowPlayingVinyl(True), lambda: shell.setVisualizerStyle("liquid"), wait, wait,
                     shot("now-playing-vinyl"), lambda: shell.setNowPlayingVinyl(False),
                     lambda: child("nowPlayingView").setProperty("open", False), wait]
            for style in ("halo", "waves"):
                todo += [lambda st=style: shell.setVisualizerStyle(st), go("visualizer"), wait, wait, shot(f"visualizer-{style}")]
            todo += [go("stations"), wait, shot("stations"), go("podcasts"), wait, shot("podcasts"),
                     lambda: QMetaObject.invokeMethod(win, "openPodcast", Q_ARG("QVariant", state["show"])), wait, wait,
                     shot("podcast")]
            todo += [lambda: managers[0].selectTheme("Ribbon"), go("home"), wait, wait, shot("theme-ribbon"),
                     lambda: managers[0].selectTheme(themes[0]), wait]
            def deck_options(lcd, crt):
                def set_options():
                    shell.setUiValue("deckLcd", lcd)
                    shell.setUiValue("deckCrt", "1" if crt else "0")
                return set_options

            def analyser_on():
                player._visualizer_enabled = True  # (the spectrum itself is faked above)
                player.visualizerChanged.emit()

            # The Deck: a retro theme opens Now Playing as a 90s hi-fi front panel
            todo += [analyser_on, deck_options("amber", False), lambda: managers[0].selectTheme("Hi-Fi Deck"),
                     lambda: child("nowPlayingView").setProperty("open", True), wait, wait, wait, shot("deck"),
                     lambda: child("nowPlayingView").setProperty("open", False), wait,
                     deck_options("green", True), lambda: child("nowPlayingView").setProperty("open", True),
                     wait, wait, wait, shot("deck-green-crt"),
                     lambda: win.resize(820, 560), wait, wait, shot("deck-small"), lambda: win.resize(1280, 800), wait,
                     lambda: child("nowPlayingView").setProperty("open", False), deck_options("amber", False), wait,
                     go("home"), wait, shot("theme-hifi-deck"),
                     lambda: managers[0].selectTheme("Beige Box"), wait, wait, shot("theme-beige-box"),
                     mark_badges, wait, wait, open_album, wait, wait, shot("badges-beige-box"),
                     open_volume, wait, shot("volume-popup-beige-box"), close_volume,
                     lambda: shell.toggleMini(), wait, wait, mini_shot("mini-beige-box"), lambda: shell.showMain(), wait,
                     lambda: managers[0].selectTheme("Hi-Fi Deck"), wait, wait, open_album, wait, shot("badges-hifi-deck"),
                     lambda: managers[0].selectTheme(themes[0]), wait, wait, open_album, wait, shot("badges"),
                     lambda: shell.setSongBadge("masterBadge", True), wait, shot("badges-master"),
                     lambda: shell.setSongBadge("masterBadge", False),
                     open_volume, wait, shot("volume-popup"), close_volume,
                     lambda: shell.toggleMini(), wait, wait, mini_shot("mini"), lambda: shell.showMain(), wait]
            # Afterimage: the neon theme, its cockpit and terminal Now Playing, and its quiet and alert versions
            def neon_mode(mode):
                return lambda: shell.setUiValue("neonNowPlaying", mode)

            def np_open(on):
                return lambda: child("nowPlayingView").setProperty("open", on)

            todo += [analyser_on, lambda: shell.setUiValue("neonTitleCard", "0"), lambda: managers[0].selectTheme("Afterimage"),
                     go("home"), wait, wait, shot("theme-afterimage"),
                     neon_mode("cockpit"), np_open(True), wait, wait, wait, shot("neon-cockpit"),
                     lambda: shell.setUiValue("neonVisStyle", "wires"), wait, wait, shot("neon-cockpit-wires"),
                     lambda: shell.setUiValue("neonVisStyle", "rain"), wait, wait, shot("neon-cockpit-rain"),
                     lambda: shell.setUiValue("neonVisStyle", ""),
                     neon_mode("terminal"), wait, wait, shot("neon-terminal"),
                     lambda: [QMetaObject.invokeMethod(child("neonTerminal"), "run", Q_ARG("QVariant", c))
                              for c in ("signal", "stats", "whoami", "vol 80", "frobnicate")],
                     lambda: QMetaObject.invokeMethod(child("neonTerminal"), "run", Q_ARG("QVariant", "help")), wait, wait,
                     shot("neon-terminal-help"),
                     lambda: shell.setUiValue("neonTermPanes", "now,wave,lyrics,queue,signal,similar"), wait, wait,
                     shot("neon-terminal-console"), lambda: shell.setUiValue("neonTermPanes", "now,wave,spectrum,lyrics,queue"),
                     lambda: shell.setUiValue("neonPhosphor", "green"), wait, shot("neon-terminal-green"),
                     lambda: shell.setUiValue("neonPhosphor", ""),
                     lambda: win.resize(820, 560), wait, wait, shot("neon-terminal-small"),
                     neon_mode("cockpit"), wait, wait, shot("neon-cockpit-small"), lambda: win.resize(1280, 800), wait,
                     np_open(False), wait,
                     lambda: managers[0].selectTheme("Afterimage Quiet"), wait, wait, shot("theme-afterimage-quiet"),
                     np_open(True), wait, wait, wait, shot("neon-cockpit-quiet"), np_open(False), wait,
                     lambda: managers[0].selectTheme("Afterimage Alert"), wait, wait, shot("theme-afterimage-alert"),
                     np_open(True), wait, wait, wait, shot("neon-cockpit-alert"), np_open(False), wait,
                     lambda: shell.setUiValue("neonTitleCard", ""), lambda: managers[0].selectTheme(themes[0]), wait, wait]

            def open_composer():
                QMetaObject.invokeMethod(win, "openComposer", Q_ARG("QVariant", COMPOSER))

            def composers_view(on):
                def set_view():
                    QMetaObject.invokeMethod(win.findChild(QObject, "pageStack").property("currentItem"), "setView",
                                             Q_ARG("QVariant", on))
                return set_view

            def search_typo(text):
                return lambda: child("searchField").setProperty("text", text)

            def scroll_to_similar():
                # the artist page, scrolled so its similar artists show
                page = win.findChild(QObject, "pageStack").property("currentItem")
                box = page.findChild(QObject, "similarArtists")
                flick = page.findChild(QObject, "artistFlick")
                if box is not None and flick is not None:
                    top = box.property("y") + box.parentItem().property("y")  # in the page's column
                    flick.setProperty("contentY", max(0.0, min(top - 110, flick.property("contentHeight") - flick.property("height"))))

            def open_folder_playlist():
                pl = next(user_lib.playlists.get(i) for i in range(user_lib.playlists.count)
                          if user_lib.playlists.get(i)["name"] == "Morning run")
                QMetaObject.invokeMethod(win, "openPlaylist", Q_ARG("QVariant", pl["id"]), Q_ARG("QVariant", pl["name"]))

            def sidebar_to_end():
                nav = child("sidebarScroll")
                nav.setProperty("contentY", max(0.0, nav.property("contentHeight") - nav.property("height")))

            todo += [open_folder_playlist, wait, sidebar_to_end, wait, shot("playlist-folders"),
                     lambda: child("sidebarScroll").setProperty("contentY", 0)]
            todo += [open_composer, wait, wait, shot("composer")]
            todo += [go("artists"), wait, composers_view(True), wait, shot("composers"), composers_view(False)]
            todo += [go("artists"), open_artist, wait, scroll_to_similar, wait, shot("similar-artists")]
            todo += [search_typo("glass orchrd"), wait, wait, shot("search-typo"), search_typo(""), wait]
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
