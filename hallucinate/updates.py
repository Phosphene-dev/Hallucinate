"""Optional check for a newer release on GitHub. Off unless turned on in Settings; when on, it asks GitHub for
the latest release at most once a day (nothing else is sent) and offers a link to it."""
import json
import logging
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Property, QObject, QSettings, QTimer, Signal, Slot

from . import __version__

logger = logging.getLogger(__name__)

LATEST_URL = "https://api.github.com/repos/bulmaspanties/Hallucinate/releases/latest"
RELEASES_PAGE = "https://github.com/bulmaspanties/Hallucinate/releases/latest"
INTERVAL_S = 24 * 3600


def version_tuple(text):
    """(major, minor, patch) from "v0.8.1" or "0.8.1"; () when it isn't a version."""
    m = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x or 0) for x in m.groups()) if m else ()


def is_newer(latest, current=__version__):
    a, b = version_tuple(latest), version_tuple(current)
    return bool(a and b and a > b)


def fetch_latest(timeout=10):
    """{"version", "url"} of the latest published release. Raises OSError/ValueError on trouble."""
    req = urllib.request.Request(LATEST_URL, headers={"User-Agent": f"Hallucinate/{__version__}",
                                                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https endpoint
        data = json.loads(resp.read(200_000))
    tag = str(data.get("tag_name") or "")
    if not version_tuple(tag):
        raise ValueError("No release version")
    return {"version": tag.lstrip("v"), "url": str(data.get("html_url") or RELEASES_PAGE)}


class UpdateChecker(QObject):
    changed = Signal()
    _done = Signal(object)

    def __init__(self, parent=None, fetch=fetch_latest):
        super().__init__(parent)
        self._settings = QSettings("hallucinate", "hallucinate")
        self._fetch = fetch
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="updates")
        self._busy = False
        self._latest = str(self._settings.value("updates/latest", ""))
        self._url = str(self._settings.value("updates/url", RELEASES_PAGE))
        self._status = ""
        self._done.connect(self._apply)
        if self.enabled and self.supported:
            QTimer.singleShot(8000, self._maybe_check)  # quietly, a little after start-up

    @Property(bool, constant=True)
    def supported(self):
        """False in the Flatpak: Flathub (or the software centre) delivers updates there."""
        return not os.environ.get("FLATPAK_ID")

    @Property(bool, notify=changed)
    def enabled(self):
        return str(self._settings.value("updates/check", "false")).lower() == "true"

    @Slot(bool)
    def setEnabled(self, on):
        self._settings.setValue("updates/check", "true" if on else "false")
        self.changed.emit()
        if on:
            self.checkNow()

    @Property(bool, notify=changed)
    def available(self):
        return self.supported and is_newer(self._latest)

    @Property(str, notify=changed)
    def latestVersion(self):
        return self._latest

    @Property(str, notify=changed)
    def releaseUrl(self):
        return self._url

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def status(self):
        return self._status

    def _maybe_check(self):
        last = float(self._settings.value("updates/lastCheck", 0) or 0)
        if self.enabled and time.time() - last >= INTERVAL_S:
            self.checkNow()

    @Slot()
    def checkNow(self):
        if self._busy or not self.supported:
            return
        self._busy = True
        self._status = "Checking…"
        self.changed.emit()

        def work():
            try:
                return {"ok": True, **self._fetch()}
            except Exception as exc:  # noqa: BLE001
                logger.info("Update check failed: %s", exc)
                return {"ok": False, "error": "Couldn't reach GitHub"}

        self._pool.submit(lambda: self._done.emit(work()))

    @Slot(object)
    def _apply(self, result):
        self._busy = False
        if result["ok"]:
            self._latest, self._url = result["version"], result["url"]
            self._settings.setValue("updates/latest", self._latest)
            self._settings.setValue("updates/url", self._url)
            self._settings.setValue("updates/lastCheck", time.time())
            self._status = (f"Hallucinate {self._latest} is available" if self.available
                            else f"You're up to date ({__version__})")
        else:
            self._status = result["error"]
        self.changed.emit()

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
