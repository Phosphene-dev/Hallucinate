"""Acting on several selected songs at once (the selection bar's actions)."""
from conftest import wait_for
from PySide6.QtCore import QObject, Signal

from hallucinate.userlib import UserLibrary


class FakePlayer(QObject):
    played = Signal(object)
    skipped = Signal(object)

    def __init__(self):
        super().__init__()
        self.calls = []

    def playList(self, tracks, index):
        self.calls.append(("play", [t["title"] for t in tracks], index))

    def enqueueAll(self, tracks):
        self.calls.append(("enqueue", [t["title"] for t in tracks]))

    def playNext(self, track):
        self.calls.append(("next", track["title"]))


def test_bulk_actions_on_selected_songs(qapp, tmp_path, db, scan, music):
    scan(music)
    by_title = {r["title"]: r["path"] for r in db._rows("SELECT title, path FROM tracks")}
    picked = [by_title["Midnight Rain"], by_title["Echoes of Dawn"], "/not/in/library.mp3"]
    player = FakePlayer()
    ul = UserLibrary(tmp_path / "lib.db", player)
    try:
        ul.playPaths(picked)
        ul.enqueuePaths(picked)
        ul.playNextPaths(picked)
        assert player.calls == [
            ("play", ["Midnight Rain", "Echoes of Dawn"], 0),  # in selection order; unknown paths dropped
            ("enqueue", ["Midnight Rain", "Echoes of Dawn"]),
            ("next", "Echoes of Dawn"), ("next", "Midnight Rain"),  # so they end up in order after the current song
        ]

        assert not ul.allLiked(picked[:2])
        ul.setLikedPaths(picked[:2], True)
        assert ul.allLiked(picked[:2]) and ul.isLiked(picked[0])
        assert wait_for(lambda: len(db._rows("SELECT path FROM likes")) == 2)
        ul.setLikedPaths(picked[:2], False)
        assert not ul.isLiked(picked[1])

        ul.setRatingPaths(picked[:2], 4)
        assert ul.rating(picked[0]) == 4 and ul.rating(picked[1]) == 4
        assert wait_for(lambda: db.ratings() == {picked[0]: 4, picked[1]: 4})
        ul.setRatingPaths(picked[:2], 0)
        assert wait_for(lambda: db.ratings() == {})

        pid = ul.addPathsToNewPlaylist("Picked", picked[:2])
        ul.openPlaylist(pid)
        assert wait_for(lambda: ul.playlistTracks.count == 2)
        assert [ul.playlistTracks.get(i)["title"] for i in range(2)] == ["Midnight Rain", "Echoes of Dawn"]
    finally:
        ul.shutdown()
