"""The one door to the internet. Every request Hallucinate makes goes through `urlopen` here, so offline mode
can close it in one place (tests/test_offline.py checks that nothing else calls urllib directly)."""
import threading
import urllib.error
import urllib.request

_lock = threading.Lock()
_offline = False


class OfflineError(urllib.error.URLError):
    """Raised instead of connecting while offline mode is on. A URLError (so an OSError), which every caller
    already treats as "no network": nothing is cached as missing and queued scrobbles stay queued."""

    def __init__(self):
        super().__init__("Offline mode is on")

    def __str__(self):
        return "Offline mode is on"


def set_offline(on):
    global _offline
    with _lock:
        _offline = bool(on)


def is_offline():
    return _offline


# No answer Hallucinate expects is anywhere near this; a server sending more is broken or hostile.
MAX_RESPONSE = 32 * 1024 * 1024


class ResponseTooLarge(OSError, ValueError):
    """The server sent more than allowed. Both an OSError and a ValueError, so every caller's existing "bad
    answer" handling catches it."""


class _Limited:
    """A response that refuses to read past `limit` bytes in total."""

    def __init__(self, resp, limit):
        self._resp, self._left = resp, limit

    def read(self, amt=-1):
        want = self._left + 1 if amt is None or amt < 0 else min(amt, self._left + 1)
        data = self._resp.read(want)
        self._left -= len(data)
        if self._left < 0:
            raise ResponseTooLarge("The server's answer was too large")
        return data

    def __getattr__(self, name):
        return getattr(self._resp, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._resp.close()
        return False


def urlopen(request, timeout=10, limit=MAX_RESPONSE):
    """Open a URL unless offline mode is on. Reading more than `limit` bytes raises ResponseTooLarge."""
    if _offline:
        raise OfflineError()
    resp = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - callers pass fixed https endpoints
    return _Limited(resp, limit)
