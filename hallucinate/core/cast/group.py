"""Several speakers playing together: AirPlay speakers and Snapcast rooms, the devices Hallucinate streams the
sound to itself (Chromecasts and DLNA renderers fetch songs by themselves, so they can't be kept in step).

Each member has its own sender with its own copy of the queue, and every command goes to all of them. They're
kept in step by time, not by talking to each other:

- AirPlay speakers start together: each is given the same moment to start from (`start_at`, a little after the
  command, long enough for every speaker to have been told), and each plays every packet a fixed latency after
  that. So they stay together to within a few milliseconds, as AirPlay's own multi-room did.
- A Snapcast room plays its stream about LEAD_S + its server's buffer after it's sent; next to AirPlay speakers
  (about two seconds behind) its feeder holds the sound back by the difference (snapcast.Feeder's delay_s).

One member is the leader: its "advanced" and "ended" are the group's (they all play the same songs at the same
time, so any member's would do). A member that drops out is left out and the rest play on; the group is lost
only when none is left."""
import threading
import time

from . import airplay

START_IN_S = 0.3  # how long after a command the AirPlay speakers start together


class GroupFeeder:
    """The members' senders as one (the same commands as snapcast.Feeder and airplay.Speaker).

    on_event(kind, tag, member): "advanced"/"ended" (the leader's) and "lost" (member None: none is left; else that
    member dropped out and the others play on)."""

    def __init__(self, on_event=None, clock=time.monotonic):
        self.on_event = on_event or (lambda kind, tag, member=None: None)
        self._clock = clock
        self._lock = threading.Lock()
        self.members = []  # [(name, feeder)]

    def add(self, name, feeder):
        """Adds a member; its events come through here from now on."""
        with self._lock:
            self.members.append((name, feeder))
        feeder.on_event = lambda kind, tag, f=feeder: self._event(f, kind, tag)

    @property
    def leader(self):
        with self._lock:
            return self.members[0][1] if self.members else None

    def _event(self, feeder, kind, tag):
        if kind == "lost":
            with self._lock:
                gone = next((m for m in self.members if m[1] is feeder), None)
                if gone is None:
                    return
                self.members.remove(gone)
                left = bool(self.members)
            try:
                feeder.close()
            except OSError:
                pass
            self.on_event("lost", None, gone[0] if left else None)
        elif feeder is self.leader:
            self.on_event(kind, tag, None)

    def _all(self, fn, together=False):
        """Does `fn(feeder)` for every member (AirPlay speakers set to start at the same moment when `together`)."""
        with self._lock:
            members = list(self.members)
        if together:
            at = self._clock() + START_IN_S
            for _name, f in members:
                if isinstance(f, airplay.Speaker):
                    f.start_at = at
        for _name, f in members:
            fn(f)

    # --- commands --------------------------------------------------------------------------------------------
    def load(self, path, start_s=0.0, end_s=0.0, tag=None, play=True):
        self._all(lambda f: f.load(path, start_s, end_s, tag=tag, play=play), together=True)

    def queue_next(self, path, tag=None, fade_s=0.0):
        self._all(lambda f: f.queue_next(path, tag=tag, fade_s=fade_s))

    def pause(self):
        self._all(lambda f: f.pause())

    def play(self):
        self._all(lambda f: f.play(), together=True)

    def seek(self, seconds):
        self._all(lambda f: f.seek(seconds), together=True)

    def stop(self):
        self._all(lambda f: f.stop())

    def position(self):
        leader = self.leader
        return leader.position() if leader is not None else (None, 0.0)

    def close(self):
        self._all(lambda f: f.close())
