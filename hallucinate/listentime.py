"""Time spent listening to internet radio and podcasts, kept in streams.db for their own small stats (they never
count toward the music's). A timer runs only while a station or episode is playing and adds what passed since
its last tick, so a pause, a seek or a song change is never counted twice."""
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .core.kinds import track_kind

TICK_MS = 15_000


class ListenClock(QObject):
    counted = Signal()  # more time was added

    def __init__(self, player, db, kind, identify, parent=None, tick_ms=TICK_MS, clock=time.monotonic):
        """`kind` is the queue entry kind to watch ("station" or "episode"); `identify(entry)` gives
        (kind stored, item id, name) for it."""
        super().__init__(parent)
        self._player, self._db, self._kind, self._identify, self._clock = player, db, kind, identify, clock
        self._since = None
        self._item = None
        self._timer = QTimer(self)
        self._timer.setInterval(tick_ms)
        self._timer.timeout.connect(self.tick)
        player.stateChanged.connect(self._update)
        player.trackChanged.connect(self._update)

    def _watching(self):
        return (self._player.playing and self._player.hasTrack
                and track_kind(self._player.current) == self._kind)

    def _update(self, *_):
        self.tick()  # count what led up to the change
        if self._watching():
            self._item = self._identify(self._player.current)
            self._since = self._clock()
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._item, self._since = None, None
            self._timer.stop()

    def tick(self):
        if self._since is None or self._item is None:
            return
        now = self._clock()
        seconds = min(now - self._since, self._timer.interval() / 1000 * 2)  # a stalled timer can't overcount
        self._since = now
        if seconds >= 1:
            kind, item_id, name = self._item
            self._db.add_listen_time(kind, item_id, name, seconds)
            self.counted.emit()

    def stop(self):
        self.tick()
        self._timer.stop()
