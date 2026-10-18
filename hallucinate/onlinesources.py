"""Where genres and artist bios come from: MusicBrainz and Wikipedia (nothing to set up), Discogs (a personal
access token, kept in the system keyring) and Last.fm (the API key set up for scrobbling)."""
import logging
import threading

import keyring
from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot

from . import keyringwait
from .core import net

logger = logging.getLogger(__name__)
KEYRING_SERVICE = "Hallucinate Discogs"
BIO_SOURCES = ("Wikipedia", "Last.fm", "Discogs")


class OnlineSources(QObject):
    changed = Signal()
    _keyring_late = Signal(object)
    _checked = Signal(str, str, str)  # token, user, error
    _stored = Signal(str)  # a keyring write finished: "" or what went wrong

    def __init__(self, lastfm_key=None, parent=None):
        super().__init__(parent)
        self._lastfm_key = lastfm_key or (lambda: "")
        self._settings = QSettings("hallucinate", "hallucinate")
        self._token, self._user = "", ""
        self._status, self._busy = "", False
        self._loaded = threading.Event()
        self._acted = False  # you connected or disconnected: a late keyring answer mustn't undo it
        self._keyring_late.connect(self._apply_keyring)
        self._checked.connect(self._on_checked)
        self._stored.connect(self._on_stored)
        # A keyring that doesn't answer is waited for in the background (see keyringwait)
        got = keyringwait.read(lambda k: keyring.get_password(KEYRING_SERVICE, k), ("token", "user"),
                               late=self._keyring_late.emit)
        if got is not None:
            self._apply_keyring(got)

    @Slot(object)
    def _apply_keyring(self, got):
        if not self._acted:
            self._token = got["values"].get("token", "") or self._token
            self._user = got["values"].get("user", "") or self._user
        if got["error"]:
            logger.info("Discogs token unavailable: %s", got["error"])
        self._loaded.set()
        self.changed.emit()

    # --- what QML shows ---------------------------------------------------------------------------------
    @Property(bool, notify=changed)
    def discogsConnected(self):
        return bool(self._token)

    @Property(str, notify=changed)
    def discogsUser(self):
        return self._user

    @Property(str, notify=changed)
    def discogsStatus(self):
        return self._status

    @Property(bool, notify=changed)
    def discogsBusy(self):
        return self._busy

    @Property(bool, notify=changed)
    def lastfmAvailable(self):
        return bool(self._lastfm_key())

    @Slot()
    def lastfmChanged(self):
        self.changed.emit()

    def _flag(self, key, default=True):
        return self._settings.value(f"sources/{key}", default, bool)

    def _set_flag(self, key, on):
        self._settings.setValue(f"sources/{key}", bool(on))
        self.changed.emit()

    @Property(bool, notify=changed)
    def genresFromDiscogs(self):
        return self._flag("genreDiscogs")

    @Slot(bool)
    def setGenresFromDiscogs(self, on):
        self._set_flag("genreDiscogs", on)

    @Property(bool, notify=changed)
    def genresFromLastfm(self):
        return self._flag("genreLastfm")

    @Slot(bool)
    def setGenresFromLastfm(self, on):
        self._set_flag("genreLastfm", on)

    @Property(bool, notify=changed)
    def fetchBios(self):
        """Look up an artist's bio when their page opens (one you wrote yourself is always shown instead)."""
        return self._flag("fetchBios", False)  # off until you switch it on

    @Slot(bool)
    def setFetchBios(self, on):
        self._set_flag("fetchBios", on)

    @Property(str, notify=changed)
    def bioSource(self):
        """Where bios come from: "" (the first that has one: Wikipedia, then Last.fm, then Discogs) or only one."""
        value = str(self._settings.value("sources/bio", "") or "")
        return value if value in BIO_SOURCES else ""

    @Slot(str)
    def setBioSource(self, source):
        self._settings.setValue("sources/bio", source if source in BIO_SOURCES else "")
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def bioSources(self):
        """[{name, ready}] — Last.fm and Discogs need setting up first."""
        return [{"name": "Wikipedia", "ready": True},
                {"name": "Last.fm", "ready": bool(self._lastfm_key())},
                {"name": "Discogs", "ready": bool(self._token)}]

    # --- Discogs token ----------------------------------------------------------------------------------
    @Slot(str)
    def connectDiscogs(self, token):
        token = (token or "").strip()
        if not token or self._busy:
            return
        if net.is_offline():
            self._status = "Offline mode is on, so the token can't be checked"
            self.changed.emit()
            return
        self._busy, self._status = True, "Checking the token…"
        self.changed.emit()

        def check():
            from .core import discogs

            try:
                user = discogs.identity(token)
                self._checked.emit(token, user or "", "")
            except (OSError, ValueError, KeyError) as exc:
                self._checked.emit(token, "", net.describe(exc))

        threading.Thread(target=check, name="discogs-token", daemon=True).start()

    @Slot(str, str, str)
    def _on_checked(self, token, user, error):
        self._busy = False
        if error:
            self._status = ("Discogs didn't accept that token" if "login" in error
                            else f"Couldn't check the token: {error}")
            self.changed.emit()
            return
        self._acted = True
        self._token, self._user = token, user
        self._status = f"Connected as {user}" if user else "Connected"
        self.changed.emit()
        self._store(lambda: (keyring.set_password(KEYRING_SERVICE, "token", token),
                             keyring.set_password(KEYRING_SERVICE, "user", user)))

    @Slot()
    def forgetDiscogs(self):
        self._acted = True
        self._token, self._user, self._status = "", "", "Disconnected from Discogs"
        self.changed.emit()

        def forget():
            for key in ("token", "user"):
                if keyring.get_password(KEYRING_SERVICE, key):
                    keyring.delete_password(KEYRING_SERVICE, key)

        self._store(forget)

    def _store(self, fn):
        """Keyring writes on a thread of their own: a locked keyring mustn't freeze the window."""
        def run():
            self._stored.emit(keyringwait.call(fn))

        threading.Thread(target=run, name="discogs-keyring", daemon=True).start()

    @Slot(str)
    def _on_stored(self, failed):
        if failed:
            self._status += f" (the system keyring couldn't be updated: {failed})"
            self.changed.emit()

    # --- for the lookups (any thread) -------------------------------------------------------------------
    def discogs_token(self, wait=3.0):
        self._loaded.wait(wait)
        return self._token

    def lastfm_key(self):
        return self._lastfm_key() or ""

    def genre_sources(self):
        use = ["MusicBrainz"]
        if self.genresFromDiscogs:
            use.append("Discogs")
        if self.genresFromLastfm:
            use.append("Last.fm")
        return tuple(use)
