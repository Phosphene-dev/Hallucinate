"""The QML side never goes online. Everything the window shows is local (covers come from the "art" image provider),
but Qt Quick will fetch any http(s) URL it is handed, for example an <img> in rich text. Text from tags, lyrics or
online lookups is drawn as plain text, and this is the second wall: the window's network access answers every
remote request with an empty reply, so a crafted tag can't phone home or slip past offline mode."""
import logging

from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtQml import QQmlNetworkAccessManagerFactory

logger = logging.getLogger(__name__)

LOCAL_SCHEMES = {"file", "qrc", "data", ""}


class LocalOnlyAccessManager(QNetworkAccessManager):
    blocked = []  # recent refused URLs, for tests and debug info

    def createRequest(self, op, request, data=None):
        url = request.url()
        if url.scheme().lower() not in LOCAL_SCHEMES:
            if len(LocalOnlyAccessManager.blocked) < 50:
                LocalOnlyAccessManager.blocked.append(url.toString())
            logger.warning("Blocked a network request from the interface: %s", url.toString()[:200])
            request = QNetworkRequest(QUrl("data:,"))
        return super().createRequest(op, request, data)


class LocalOnlyFactory(QQmlNetworkAccessManagerFactory):
    def create(self, parent):
        return LocalOnlyAccessManager(parent)


_factory = LocalOnlyFactory()  # the engine doesn't take ownership; keep it alive for the app's lifetime


def install(engine):
    engine.setNetworkAccessManagerFactory(_factory)
