"""Sounds like this: measuring how a song sounds (tempo, key, timbre) from made-up audio, finding the songs
closest to one with the choices from Settings, listening to the library in the background only when it may,
and radio picking by sound."""
import time
import wave

import numpy as np
import pytest

from hallucinate.core import soundlike as sl

R = 44100


def tone(bpm, notes, seconds=40, bright=1.0, seed=0):
    """A chord of `notes` (Hz) with a noisy hit on every beat, stereo float32 at R."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * R)) / R
    x = np.zeros_like(t)
    for f in notes:
        for h in range(1, 6):
            x += np.sin(2 * np.pi * f * h * t) / h ** (2.0 / bright)
    x *= 0.05
    x += np.exp(-(t % (60 / bpm)) * 30) * rng.normal(0, 0.3, len(t))
    return np.stack([x, x], 1).astype(np.float32)


def hz(semitone):  # from middle C
    return 440.0 * 2 ** ((semitone - 9) / 12)


def collect(x, start=0.0):
    c = sl.Collector(start)
    for i in range(0, len(x), 4096):
        if not c.add(x[i:i + 4096], R):
            break
    return c.result()


def test_tempo_and_key_are_heard():
    a_minor = collect(tone(120, [hz(9) / 2, hz(12) / 2, hz(16) / 2]))
    assert abs(a_minor["bpm"] - 120) < 2 and sl.key_name(a_minor["key"]) == "A minor"
    g_major = collect(tone(140, [hz(7), hz(11), hz(14)]))
    assert abs(g_major["bpm"] - 140) < 2 and sl.key_name(g_major["key"]) == "G major"
    assert a_minor["vec"].shape == (sl.DIMS,) and np.all(np.isfinite(a_minor["vec"]))


def test_silence_and_too_little_are_not_measured():
    assert collect(np.zeros((R * 20, 2), np.float32)) is None
    assert collect(tone(120, [440.0], seconds=3)) is None


def test_the_window_and_a_short_song():
    assert sl.window(0) == 0 and sl.window(300) == sl.START_S and sl.window(80) == 10.0
    c = sl.Collector(start=1000)  # (the song ends long before: what came before is measured)
    x = tone(100, [hz(0)], seconds=20)
    for i in range(0, len(x), 4096):
        c.add(x[i:i + 4096], R)
    assert c.result() is not None
    c = sl.Collector(start=5)  # it stops asking once it has its minute
    asked = [c.add(x[:R], R) for _ in range(70)]
    assert asked[-1] is False and asked[10] is True


def test_the_camelot_wheel_and_tempo():
    assert sl.camelot(0) == (8, "B") and sl.camelot(21) == (8, "A") and sl.camelot(7) == (9, "B")
    assert sl.keys_mix(0, 21) and sl.keys_mix(0, 7) and sl.keys_mix(0, 5) and not sl.keys_mix(0, 6)
    assert sl.keys_mix(0, sl.NO_KEY)
    assert sl.tempo_gap(120, 60) == 0 and sl.tempo_gap(120, 0) == 0 and sl.tempo_gap(120, 132) > 0.1


# --- the library -------------------------------------------------------------------------------------------
def song(i, artist, title, duration=200.0, mtime=1):
    return {"path": f"/m/{artist}/{title}.flac", "mtime": mtime, "size": 1, "title": title, "artist": artist,
            "album_artist": artist, "aa_tag": 1, "album": "A", "album_key": f"{artist}|A", "track_no": i, "disc_no": 1,
            "year": 2000, "genre": "", "duration": duration, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0,
            "sample_rate": 44100}


@pytest.fixture
def db(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "lib.db")
    rng = np.random.default_rng(1)
    rows = []
    # two kinds of music: "calm" songs near one point, "loud" ones near another; tempos around 90 and 150
    for k, (artist, centre, bpm) in enumerate((("Calm", 0.0, 90), ("Hush", 0.2, 92), ("Loud", 5.0, 150), ("Roar", 5.2, 148))):
        for i in range(6):
            t = song(i, artist, f"{artist} {i}")
            db.upsert_track(t)
            vec = (np.full(sl.DIMS, centre) + rng.normal(0, 0.3, sl.DIMS)).astype(np.float32)
            rows.append({"path": t["path"], "mtime": 1, "result": {"vec": vec, "bpm": bpm + i * 0.5, "key": (k * 3) % 24}})
    db.upsert_track(song(0, "Short", "Blip", duration=3.0))  # too short to measure
    db.upsert_track(song(0, "New", "Unheard"))
    db.commit()
    sl.store(db, rows)
    yield db
    db.close()


def test_what_is_left_to_measure(db):
    assert sl.counts(db) == (24, 25)
    todo = sl.to_measure(db)
    assert [t["path"] for t in todo] == ["/m/New/Unheard.flac"]
    db.conn.execute("UPDATE tracks SET mtime = 2 WHERE path = '/m/Calm/Calm 0.flac'")  # (the file changed)
    assert {t["path"] for t in sl.to_measure(db)} == {"/m/New/Unheard.flac", "/m/Calm/Calm 0.flac"}
    sl.forget(db)
    assert sl.counts(db) == (0, 25)


def test_songs_that_sound_alike(db):
    index = sl.Index().load(db)
    assert len(index) == 24
    seed = "/m/Calm/Calm 0.flac"
    picks = index.pick([seed], size=8, order="alike", tempo=False, per_artist=0)
    assert seed not in picks and all("/Calm/" in p or "/Hush/" in p for p in picks)
    capped = index.pick([seed], size=8, per_artist=2, tempo=False)
    assert max(sum(1 for p in capped if f"/{a}/" in p) for a in ("Calm", "Hush", "Loud", "Roar")) <= 2
    others = index.pick([seed], size=5, same_artist=False, tempo=False)
    assert others and not any("/Calm/" in p for p in others)
    assert "/m/Hush/Hush 0.flac" not in index.pick([seed], size=30, exclude={"/m/Hush/Hush 0.flac"})
    assert not any("/Hush/" in p for p in index.pick([seed], size=30, left_out_artists={"hush"}))
    flow = index.pick([seed], size=10, order="flow", per_artist=0)
    assert sorted(flow) == sorted(index.pick([seed], size=10, order="alike", per_artist=0))
    assert index.pick(["/m/not/measured.flac"]) == []


def test_tempo_keeps_close(db):
    db.conn.execute("UPDATE sound_features SET bpm = 125 WHERE path IN "
                    "('/m/Hush/Hush 0.flac', '/m/Hush/Hush 1.flac', '/m/Hush/Hush 2.flac')")  # (a third faster)
    db.commit()
    index = sl.Index().load(db)
    near = index.pick(["/m/Calm/Calm 0.flac"], size=3, tempo=True, same_artist=False, per_artist=0)
    assert sorted(near) == ["/m/Hush/Hush 3.flac", "/m/Hush/Hush 4.flac", "/m/Hush/Hush 5.flac"]
    loose = index.pick(["/m/Calm/Calm 0.flac"], size=6, tempo=False, same_artist=False, per_artist=0)
    assert len(loose) == 6 and all("/Hush/" in p for p in loose)


# --- in the app --------------------------------------------------------------------------------------------
class FakeAnalyser:
    def __init__(self, results=None):
        self.jobs, self.cancelled, self.results = [], 0, results

    def submit(self, path, kind, then, envelope=False, first=False, extra=None):
        self.jobs.append((path, kind, extra))
        vec = np.arange(sl.DIMS, dtype=np.float32) + len(self.jobs) * 0.01
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda: then({"vec": vec, "bpm": 120.0, "key": 0, "keyStrength": 0.8}))

    def cancel(self):
        self.cancelled += 1

    def shutdown(self):
        pass


class FakePlayer:
    def __init__(self):
        from PySide6.QtCore import QObject, Signal

        class P(QObject):
            stateChanged = Signal()

        self.q = P()
        self.stateChanged = self.q.stateChanged
        self.playing = False
        self._queue = []


class FakeShell:
    def __init__(self):
        from PySide6.QtCore import QObject, Signal

        class S(QObject):
            featuresChanged = Signal()

        self.s = S()
        self.featuresChanged = self.s.featuresChanged
        self.features = {}

    def featureOn(self, name):  # noqa: N802
        return self.features.get(name, True)


class FakeLib:
    def __init__(self):
        self.played, self.queued = [], []

    def playPaths(self, paths):  # noqa: N802
        self.played = list(paths)

    def enqueuePaths(self, paths):  # noqa: N802
        self.queued = list(paths)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    QSettings().remove("soundsLike")
    yield
    QSettings().remove("soundsLike")


def test_listening_in_the_background_only_when_it_may(qapp, db, tmp_path, settings):
    from conftest import wait_for

    from hallucinate.likethis import SoundsLike

    sl.forget(db)
    player, shell, analyser = FakePlayer(), FakeShell(), FakeAnalyser()
    player.playing = True
    s = SoundsLike(tmp_path / "lib.db", player, FakeLib(), shell, analyser, FakeAnalyser(), battery=lambda: False, autostart=False)
    try:
        s._recount()
        assert wait_for(lambda: s.total == 25, 10)
        assert not s.running and s.waiting == "playing" and not analyser.jobs  # (something's playing)
        player.playing = False
        player.stateChanged.emit()
        s._soon.stop()
        s._consider()
        assert wait_for(lambda: s.measured == 25 and not s.running, 15), (s.measured, s.total)
        assert len(analyser.jobs) == 25 and all(k == "features" for _, k, _ in analyser.jobs)
        assert all(e["low"] for _, _, e in analyser.jobs)
        s._recount()
        assert wait_for(lambda: s.measured == 25 and s.total == 25, 10)  # (and they were saved)

        sl.forget(db)
        s.setPaused(True)
        s._recount()
        assert wait_for(lambda: s.measured == 0, 10)
        assert not s.running and s.waiting == "paused"
        s.measureNow()  # (unpauses, and runs whatever "when" says)
        assert wait_for(lambda: s.measured == 25, 15)
        sl.forget(db)
        s.setWhen("ask")
        s._recount()
        assert wait_for(lambda: s.measured == 0 and s.waiting == "ask", 10)
        shell.features["soundsLike"] = False
        shell.featuresChanged.emit()
        assert not s.enabled and s.waiting == "off"
    finally:
        s.shutdown()


def test_on_battery_it_waits(qapp, db, tmp_path, settings):
    from conftest import wait_for

    from hallucinate.likethis import SoundsLike

    sl.forget(db)
    analyser = FakeAnalyser()
    s = SoundsLike(tmp_path / "lib.db", None, FakeLib(), FakeShell(), analyser, FakeAnalyser(), battery=lambda: True, autostart=False)
    try:
        s._recount()
        assert wait_for(lambda: s.total == 25, 10)
        assert s.waiting == "battery" and not analyser.jobs
        s.setNotOnBattery(False)
        assert wait_for(lambda: s.measured == 25, 15)
    finally:
        s.shutdown()


def test_play_queue_and_an_unmeasured_song(qapp, db, tmp_path, settings):
    from conftest import wait_for

    from hallucinate.likethis import SoundsLike

    lib, quick = FakeLib(), FakeAnalyser()
    s = SoundsLike(tmp_path / "lib.db", FakePlayer(), lib, FakeShell(), FakeAnalyser(), quick, battery=lambda: False, autostart=False)
    said = []
    s.message.connect(said.append)
    try:
        s.setWhen("ask")
        s.setSize(25)
        s.playLike("/m/Calm/Calm 0.flac")
        assert wait_for(lambda: lib.played, 10)
        assert lib.played[0] == "/m/Calm/Calm 0.flac" and len(lib.played) > 5
        s.queueLike("/m/Loud/Loud 0.flac")
        assert wait_for(lambda: lib.queued, 10)
        assert "/m/Loud/Loud 0.flac" not in lib.queued
        lib.played = []
        s.playLike("/m/New/Unheard.flac")  # not measured yet: it's listened to first
        assert wait_for(lambda: lib.played, 10)
        assert quick.jobs and quick.jobs[0][0] == "/m/New/Unheard.flac" and lib.played[0] == "/m/New/Unheard.flac"
        said.clear()
        s.playLike("http://radio.example/stream")
        assert said and "this computer" in said[0]
    finally:
        s.shutdown()


def test_radio_by_sound(qapp, db, tmp_path, settings):
    from hallucinate.library import Library
    from hallucinate.likethis import SoundsLike

    s = SoundsLike(tmp_path / "lib.db", None, None, FakeShell(), FakeAnalyser(), FakeAnalyser(), battery=lambda: False, autostart=False)
    try:
        s.setRadioPicks("sound")
        got = Library._radio_by_sound(db, s, "sound", ["/m/Loud/Loud 0.flac"], set(), 6)
        # (two songs an artist at most, as radio always has: four by sound, the rest the usual way)
        assert len(got) == 6 and all("/Loud/" in t["path"] or "/Roar/" in t["path"] for t in got[:4])
        both = Library._radio_by_sound(db, s, "both", ["/m/Loud/Loud 0.flac"], set(), 6)
        assert len(both) <= 6 and both[0]["path"] in {t["path"] for t in got}
        shell = FakeShell()
        shell.features["soundsLike"] = False
        s._shell = shell
        assert s.radio_mode() == "together"
    finally:
        s.shutdown()


def test_the_real_helper_listens(qapp, tmp_path):
    from conftest import wait_for

    from hallucinate.analysis import Analyser

    path = tmp_path / "beat.wav"
    x = (tone(128, [hz(9) / 2, hz(12) / 2, hz(16) / 2], seconds=20)[:, 0] * 20000).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(R)
        w.writeframes(x.tobytes())
    analyser, got = Analyser(), {}
    t0 = time.monotonic()
    analyser.submit(path, "features", lambda r: got.__setitem__("r", r), extra={"start": 2.0, "low": True})
    try:
        assert wait_for(lambda: "r" in got, 30)
        r = got["r"]
        assert r is not None and r["vec"].shape == (sl.DIMS,) and abs(r["bpm"] - 128) < 3, r
        assert time.monotonic() - t0 < 30
    finally:
        analyser.shutdown()
