"""Background work: one thread pool, one shared ExifTool, and image decoding off the UI thread."""
from __future__ import annotations

import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QImage, QImageReader, QTransform

THUMB_PX = 320  # longest side kept in the thumbnail cache
PREVIEW_PX = 2400


def friendly(exc: BaseException) -> str:
    """Plain-language message for anything a worker can raise."""
    text = str(exc)
    if "exiftool" in text.lower() or "exiftool" in type(exc).__name__.lower():
        return ("ExifTool, the helper that reads photo metadata, could not be started. "
                "Make sure the exiftool folder is still next to the app, or reinstall it.")
    if isinstance(exc, FileNotFoundError):
        return "That folder could not be found. Check that the drive is connected and try again."
    if isinstance(exc, PermissionError):
        return "Windows would not let the app read that folder. Check its permissions and try again."
    if isinstance(exc, OSError):
        return f"The folder could not be read ({exc.strerror or text})."
    return f"Something went wrong: {text or type(exc).__name__}."


def decode(data: bytes, rotation: int, max_px: int) -> QImage | None:
    img = QImage.fromData(data)
    if img.isNull():
        return None
    if rotation % 360:
        img = img.transformed(QTransform().rotate(rotation))
    if max(img.width(), img.height()) > max_px:
        img = img.scaled(max_px, max_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return img


def read_scaled(path: str, max_px: int) -> QImage | None:
    """Fallback for files exiftool has no embedded preview for (plain JPEGs)."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > max_px:
        reader.setScaledSize(size.scaled(QSize(max_px, max_px), Qt.KeepAspectRatio))
    img = reader.read()
    return None if img.isNull() else img


class Engine(QObject):
    """Runs functions on worker threads and hands results back on the UI thread."""

    _finished = Signal(object, object)

    def __init__(self, make_exiftool=None):
        super().__init__()
        self._finished.connect(self._dispatch)
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="odometer")
        self._make_exiftool = make_exiftool
        self._et = None
        self._et_lock = threading.Lock()
        self._closed = False
        self.pending = 0  # jobs submitted whose callback has not run yet (UI thread only)
        # ponytail: oldest-first cache capped at 600 thumbs (~100 MB worst case), use a byte budget if needed
        self._thumbs: OrderedDict[str, QImage | None] = OrderedDict()

    # -- generic jobs --

    def run(self, fn, done=None, failed=None) -> None:
        """Call fn() on a worker; then done(result) or failed(message) on the UI thread."""
        self.pending += 1

        def job():
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001 - every failure becomes a UI message
                self._finished.emit(failed, friendly(exc))
            else:
                self._finished.emit(done, result)

        self._pool.submit(job)

    @Slot(object, object)
    def _dispatch(self, callback, value) -> None:
        self.pending -= 1
        if callback and not self._closed:
            callback(value)

    # -- exiftool --

    def et(self):
        """The shared ExifTool, started on first use. Call from worker threads only."""
        with self._et_lock:
            if self._et is None:
                if self._make_exiftool:
                    self._et = self._make_exiftool()
                else:
                    from ..exif import ExifTool
                    self._et = ExifTool()
            return self._et

    # -- images --

    def thumb(self, path: str) -> QImage | None:
        return self._thumbs.get(path)

    def has_thumb(self, path: str) -> bool:
        return path in self._thumbs

    def load_thumbs(self, paths: list[str], done) -> None:
        """Fetch and decode the thumbnails not cached yet, then done(error message or None)."""
        missing = [p for p in paths if p not in self._thumbs]
        if not missing:
            done(None)
            return

        def work():
            found = self.et().thumbnails(missing)
            out = {}
            for p in missing:
                hit = found.get(p)
                out[p] = decode(hit[0], hit[1], THUMB_PX) if hit else None
                if out[p] is None:
                    out[p] = read_scaled(p, THUMB_PX)
            return out

        def store(images, error=None):
            self._thumbs.update(images)
            while len(self._thumbs) > 600:
                self._thumbs.popitem(last=False)
            done(error)

        self.run(work, store, lambda message: store(dict.fromkeys(missing), message))

    def load_preview(self, path: str, done) -> None:
        def work():
            hit = self.et().preview(path)
            img = decode(hit[0], hit[1], PREVIEW_PX) if hit else None
            return path, img or read_scaled(path, PREVIEW_PX)

        self.run(work, lambda r: done(*r), lambda _msg: done(path, None))

    def close(self) -> None:
        self._closed = True
        self._pool.shutdown(wait=True, cancel_futures=True)
        if self._et is not None:
            self._et.close()
