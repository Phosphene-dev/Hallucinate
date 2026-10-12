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


def urlopen(request, timeout=10):
    if _offline:
        raise OfflineError()
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - callers pass fixed https endpoints
