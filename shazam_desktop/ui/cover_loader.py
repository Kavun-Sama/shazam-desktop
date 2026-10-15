"""Asynchronous cover-art download on top of Qt's own network stack."""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

_TIMEOUT_MS = 8000


class CoverLoader(QObject):
    """Downloads one image at a time; a newer request cancels the older one."""

    loaded = Signal(QPixmap)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None

    def load(self, url: str) -> None:
        self.cancel()
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setTransferTimeout(_TIMEOUT_MS)
        reply = self._manager.get(request)
        self._reply = reply
        reply.finished.connect(partial(self._on_finished, reply))

    def cancel(self) -> None:
        reply, self._reply = self._reply, None
        if reply is not None:
            reply.disconnect(self)
            reply.abort()
            reply.deleteLater()

    def _on_finished(self, reply: QNetworkReply) -> None:
        if reply is not self._reply:
            return
        self._reply = None
        data = reply.readAll() if reply.error() == QNetworkReply.NetworkError.NoError else None
        reply.deleteLater()
        if not data:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.loaded.emit(pixmap)
