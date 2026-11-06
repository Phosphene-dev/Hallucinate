"""The songs a live stream plays, one straight on into the next: for the devices Hallucinate streams sound to itself
(a Snapcast server, an AirPlay speaker) rather than handing them a link to fetch.

Each song is a WAV file the decoding helper wrote in the stream's format (see Casting.media_for). A `Queue` holds
the song playing and the one after it, hands out the audio a slice at a time (pull), and keeps time: a device
plays what it's sent a little later (its buffer, and how far ahead the sender runs), so the queue remembers a
song that has just been sent to the end until it has been heard to the end, and says where the listener is
(position). It's driven by the sender's thread and the window's at once, so everything goes under one lock."""
import threading
import wave


class FormatError(OSError):
    pass


class Source:
    """A WAV file being read, from a frame on, up to an end (a CUE sheet song is part of a file)."""

    def __init__(self, path, rate, channels=2, width=2, start_s=0.0, end_s=0.0, tag=None):
        self.tag = tag
        self.rate = rate
        self.wav = wave.open(path, "rb")
        if (self.wav.getframerate(), self.wav.getnchannels(), self.wav.getsampwidth()) != (rate, channels, width):
            self.wav.close()
            raise FormatError("the song wasn't got ready in the stream's format")
        self.frame = channels * width
        self.frames = self.wav.getnframes()
        self.end = min(self.frames, int(end_s * rate)) if end_s else self.frames
        self.at = max(0, min(self.end, int(start_s * rate)))
        self.wav.setpos(self.at)

    def read(self, frames):
        frames = max(0, min(frames, self.end - self.at))
        data = self.wav.readframes(frames) if frames else b""
        self.at += len(data) // self.frame
        return data

    def seek(self, seconds):
        self.at = max(0, min(self.end, int(seconds * self.rate)))
        self.wav.setpos(self.at)

    def close(self):
        try:
            self.wav.close()
        except Exception:  # noqa: BLE001
            pass


class Queue:
    """The song playing and the one to go on into. `clock` is time.monotonic (tests pass their own)."""

    def __init__(self, rate, clock, channels=2, width=2):
        self.rate, self.channels, self.width = rate, channels, width
        self.frame = channels * width
        self._clock = clock
        self.lock = threading.RLock()
        self.current = self.next = None
        self.paused = True
        self._ending = None  # (tag, seconds it ends at, when that's heard): a song still playing out of the buffer
        self._previous = None  # that song, kept to go back into (see rewind)

    def _source(self, path, start_s=0.0, end_s=0.0, tag=None):
        return Source(path, self.rate, self.channels, self.width, start_s, end_s, tag)

    # --- commands --------------------------------------------------------------------------------------------
    def load(self, path, start_s=0.0, end_s=0.0, tag=None, play=True):
        source = self._source(path, start_s, end_s, tag)
        with self.lock:
            self._forget_previous()
            for old in (self.current, self.next):
                if old is not None:
                    old.close()
            self.current, self.next = source, None
            self.paused = not play

    def queue_next(self, path, tag=None):
        source = self._source(path, tag=tag) if path else None
        with self.lock:
            if self.next is not None:
                self.next.close()
            self.next = source

    def pause(self):
        with self.lock:
            self.paused = True

    def play(self):
        with self.lock:
            self.paused = False

    def seek(self, seconds):
        with self.lock:
            self._forget_previous()
            if self.current is not None:
                self.current.seek(seconds)

    def stop(self):
        with self.lock:
            self._forget_previous()
            for old in (self.current, self.next):
                if old is not None:
                    old.close()
            self.current = self.next = None
            self.paused = True

    def close(self):
        self.stop()

    @property
    def playing(self):
        with self.lock:
            return not self.paused and self.current is not None

    # --- time ------------------------------------------------------------------------------------------------
    def position(self, behind):
        """(tag, seconds) of what's being heard now, `behind` seconds after it was handed out (a song that just
        ended is still heard for that long)."""
        with self.lock:
            now = self._clock()
            if self._ending is not None:
                tag, end, heard = self._ending
                if now < heard:
                    return tag, max(0.0, end - (heard - now))
                self._ending = None
            src = self.current
            if src is None:
                return None, 0.0
            return src.tag, max(0.0, src.at / self.rate - behind)

    def _forget_previous(self):
        self._ending = None
        if self._previous is not None:
            self._previous.close()
            self._previous = None

    def rewind(self, seconds):
        """Goes back `seconds` (what was sent but a device dropped unheard: see AirPlay's pause), to what's being
        heard. That can be the song before, still playing out of the buffer: it becomes the one playing again
        (the one after it next, from its start), and True says so (its "advanced" or "ended" didn't happen)."""
        with self.lock:
            prev, ending = self._previous, self._ending
            self._previous = self._ending = None
            if prev is not None and ending is not None and self._clock() < ending[2]:
                if self.current is not None:
                    if self.next is not None:
                        self.next.close()
                    self.current.seek(0.0)
                    self.next = self.current
                prev.seek(max(0.0, ending[1] - (ending[2] - self._clock())))
                self.current = prev
                return True
            if prev is not None:
                prev.close()
            if self.current is not None and seconds > 0:
                self.current.seek(max(0.0, self.current.at / self.rate - seconds))
            return False

    def pull(self, frames, behind):
        """The next `frames` of audio (None while paused or with nothing to play), padded with silence where the
        queue runs out, and the events that will be heard `behind` seconds from now: [("advanced", tag)] when it
        goes straight on into the next song, [("ended", tag)] when the last song ends (and it pauses)."""
        with self.lock:
            if self.paused or self.current is None:
                return None, []
            events = []
            want = frames * self.frame
            src = self.current
            data = src.read(frames)
            if len(data) < want:  # this song is over: on into the next, or silence
                nxt = self.next
                self._forget_previous()
                self._previous = src  # (still heard for `behind`: see rewind)
                self._ending = (src.tag, src.end / self.rate, self._clock() + behind)
                self.current, self.next = nxt, None
                if nxt is not None:
                    data += nxt.read(frames - len(data) // self.frame)
                    events.append(("advanced", nxt.tag))
                else:
                    self.paused = True
                    events.append(("ended", src.tag))
                data += b"\0" * (want - len(data))
            return data, events
