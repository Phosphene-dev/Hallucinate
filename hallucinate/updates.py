"""Optional check for a newer release on GitHub. Off unless turned on in Settings; when on, it asks GitHub for
the latest release at most once a day (nothing else is sent) and offers a link to it. Where the app can update
itself (selfupdate.install_kind), it can also download, check and install the release."""
import json
import logging
import os
import re
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Property, QCoreApplication, QObject, QSettings, QTimer, Signal, Slot

from . import __version__, selfupdate
from .core import net

logger = logging.getLogger(__name__)

LATEST_URL = "https://api.github.com/repos/Phosphene-dev/Hallucinate/releases/latest"
RELEASES_PAGE = "https://github.com/Phosphene-dev/Hallucinate/releases/latest"
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
    with net.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read(200_000))
    tag = str(data.get("tag_name") or "")
    numbers = version_tuple(tag)
    if not numbers:
        raise ValueError("No release version")
    assets = [{"name": a.get("name"), "url": a.get("browser_download_url"), "size": a.get("size"),
               "digest": a.get("digest")} for a in data.get("assets") or [] if isinstance(a, dict)]
    url = str(data.get("html_url") or "")
    if not url.startswith("https://github.com/Phosphene-dev/Hallucinate/"):
        url = RELEASES_PAGE  # only ever open our own release page
    # just the numbers: nothing else from the response is shown or compared
    return {"version": ".".join(map(str, numbers)), "url": url, "assets": assets}


def system_package(frozen=None, module=__file__):
    """True for a copy installed by the system package manager (AUR and other distro packages), which updates
    it; the AppImage and the Windows and macOS builds are frozen or mounted elsewhere."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    return not frozen and not os.environ.get("APPIMAGE") and str(module).startswith("/usr/")


class UpdateChecker(QObject):
    changed = Signal()
    _done = Signal(object)
    _installProgress = Signal(object)

    def __init__(self, parent=None, fetch=fetch_latest, kind=None, download=selfupdate.download):
        super().__init__(parent)
        self._settings = QSettings("hallucinate", "hallucinate")
        self._fetch = fetch
        self._kind = selfupdate.install_kind() if kind is None else kind
        self._download = download
        self._installing = False
        self._progress = 0.0
        self._cancel = False
        self._installProgress.connect(self._apply_install)
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
        """False in the Flatpak and system packages: the software centre or package manager updates those."""
        return not os.environ.get("FLATPAK_ID") and not system_package()

    @Property(bool, constant=True)
    def canInstall(self):
        """This copy can install updates itself (the Windows installer build or a writable AppImage)."""
        return bool(self._kind)

    @Property(bool, notify=changed)
    def installing(self):
        return self._installing

    @Property(float, notify=changed)
    def installProgress(self):
        return self._progress

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
        if self.enabled and not net.is_offline() and time.time() - last >= INTERVAL_S:
            self.checkNow()

    @Property(bool, notify=changed)
    def offline(self):
        return net.is_offline()

    @Slot()
    def checkNow(self):
        if self._busy or not self.supported:
            return
        if net.is_offline():
            self._status = "Offline mode is on"
            self.changed.emit()
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

    @Slot()
    def installNow(self):
        """Fetch the latest release, download this platform's build, check it, then install it and restart."""
        if self._installing or self._busy or not self._kind or not self.supported:
            return
        if net.is_offline():
            self._status = "Offline mode is on"
            self.changed.emit()
            return
        self._installing, self._progress, self._cancel = True, 0.0, False
        self._status = "Downloading the update…"
        self.changed.emit()
        kind = self._kind

        def work():
            try:
                latest = self._fetch()
                if not is_newer(latest["version"]):
                    return {"error": f"You're up to date ({__version__})"}
                asset = selfupdate.pick_asset(latest.get("assets"), latest["version"], kind)
                if not asset:
                    return {"error": "This release has no download for this install; opening its page",
                            "url": latest["url"]}
                if kind == "appimage":  # beside the AppImage, so the swap is a rename on one filesystem
                    folder = os.path.dirname(os.environ["APPIMAGE"])
                else:
                    folder = tempfile.gettempdir()
                dest = os.path.join(folder, f".{asset['name']}.part")
                self._download(asset, dest, lambda f: self._installProgress.emit({"progress": f}), lambda: self._cancel)
                return {"path": dest, "version": latest["version"]}
            except ValueError as exc:
                logger.warning("Update download rejected: %s", exc)
                return {"error": str(exc)}
            except Exception as exc:  # noqa: BLE001
                logger.info("Update download failed: %s", exc)
                return {"error": "Update cancelled" if self._cancel else "Couldn't download the update"}

        self._pool.submit(lambda: self._installProgress.emit({"done": work()}))

    @Slot()
    def cancelInstall(self):
        self._cancel = True

    @Slot(object)
    def _apply_install(self, update):
        if "progress" in update:
            self._progress = float(update["progress"])
            self._status = f"Downloading the update… {int(self._progress * 100)}%"
            self.changed.emit()
            return
        result = update["done"]
        self._installing = False
        if "error" in result:
            self._status = result["error"]
            self.changed.emit()
            if result.get("url"):
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices

                QDesktopServices.openUrl(QUrl(result["url"]))
            return
        self._status = f"Installing Hallucinate {result['version']}…"
        self.changed.emit()
        try:
            if self._kind == "windows":
                selfupdate.run_windows_installer(result["path"])
            else:
                selfupdate.swap_appimage(result["path"], os.environ["APPIMAGE"], os.getpid())
        except OSError as exc:
            logger.warning("Couldn't install the update: %s", exc)
            self._status = "Couldn't install the update"
            self.changed.emit()
            return
        QTimer.singleShot(400, QCoreApplication.quit)

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
