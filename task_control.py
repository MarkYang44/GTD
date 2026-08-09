"""Thread-safe primitives used to control download attempts."""

from __future__ import annotations

import threading

from download_errors import DownloadCancelled


class CancellationToken:
    """A cooperative, one-way cancellation signal."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise DownloadCancelled()
