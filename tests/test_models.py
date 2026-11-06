"""The list models QML pages read: a playlist's header (how long it lasts, songs in it twice) is worked out in
Python, without copying every song into the page."""
import time


def test_a_playlists_length_and_repeats(qapp):
    from hallucinate.models import TRACK_KEYS, DictModel

    m = DictModel(TRACK_KEYS)
    songs = [{"path": f"/m/{i % 1500}.flac", "duration": 200.5} for i in range(2000)]
    m.set_items(songs)
    started = time.perf_counter()
    s = m.summary()
    assert time.perf_counter() - started < 0.05  # (a big list: at once)
    assert s["twice"] == 500 and abs(s["seconds"] - 2000 * 200.5) < 1e-6
    assert m.paths()[:2] == ["/m/0.flac", "/m/1.flac"]
    m.set_items([{"path": "/x", "duration": None}])
    assert m.summary() == {"seconds": 0.0, "twice": 0}
