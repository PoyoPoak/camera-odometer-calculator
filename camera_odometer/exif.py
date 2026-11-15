"""Metadata and embedded previews, read through one long-lived ExifTool process."""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from .models import Shot

_READ_TAGS = ["-Make", "-Model", "-SerialNumber", "-InternalSerialNumber",
              "-DateTimeOriginal", "-ShutterCount", "-ImageCount"]
_ROTATION = {3: 180, 6: 90, 8: 270}  # EXIF Orientation -> degrees clockwise


def find_exiftool() -> list[str]:
    """argv prefix for ExifTool: frozen bundle, then vendor/, then PATH."""
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "exiftool" / "exiftool.exe"
        if bundled.exists():
            return [str(bundled)]
    vendor = Path(__file__).resolve().parent.parent / "vendor"
    if os.name == "nt" and (vendor / "exiftool-win" / "exiftool.exe").exists():
        return [str(vendor / "exiftool-win" / "exiftool.exe")]
    if os.name != "nt" and (vendor / "exiftool-perl" / "exiftool").exists():
        return ["perl", str(vendor / "exiftool-perl" / "exiftool")]
    on_path = shutil.which("exiftool")
    if on_path:
        return [on_path]
    raise FileNotFoundError("ExifTool not found (bundle, vendor/ or PATH)")


class ExifTool:
    """One `-stay_open` process. Calls are serialized by a lock, so any thread may use it."""

    def __init__(self, command: list[str] | None = None):
        self._lock = threading.Lock()
        self._seq = 0
        self._proc = subprocess.Popen(
            [*(command or find_exiftool()), "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def read(self, paths: list[str]) -> list[Shot]:
        """One Shot per path, in order. A file ExifTool cannot read gives a blank Shot."""
        rows = self._json(["-fast", *_READ_TAGS], paths)
        return [_shot(p, rows.get(_key(p), {})) for p in paths]

    def thumbnails(self, paths: list[str]) -> dict[str, tuple[bytes, int]]:
        """{path: (JPEG bytes, rotation)} for the paths that embed a thumbnail."""
        rows = self._json(["-b", "-ThumbnailImage", "-Orientation#"], paths)
        found = ((p, _image(rows.get(_key(p), {}), "ThumbnailImage")) for p in paths)
        return {p: image for p, image in found if image}

    def preview(self, path: str) -> tuple[bytes, int] | None:
        for tag in ("PreviewImage", "JpgFromRaw"):
            image = _image(self._json(["-b", f"-{tag}", "-Orientation#"], [path]).get(_key(path), {}), tag)
            if image:
                return image
        return None

    def close(self) -> None:
        with self._lock:
            if self._proc.poll() is None:
                try:
                    self._proc.stdin.write(b"-stay_open\nFalse\n")
                    self._proc.stdin.close()
                    self._proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    self._proc.kill()

    def __enter__(self) -> ExifTool:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _json(self, args: list[str], paths: list[str]) -> dict[str, dict]:
        """Run one command over `paths`; rows keyed by normalized SourceFile."""
        if not paths:
            return {}
        out = self._execute(["-j", "-charset", "filename=utf8", *args, *paths])
        return {_key(row["SourceFile"]): row for row in json.loads(out or b"[]")}

    def _execute(self, args: list[str]) -> bytes:
        with self._lock:
            self._seq += 1
            ready = f"{{ready{self._seq}}}".encode()
            lines = "".join(f"{a}\n" for a in [*args, f"-execute{self._seq}"])
            self._proc.stdin.write(lines.encode("utf-8"))
            self._proc.stdin.flush()
            out = bytearray()
            for line in iter(self._proc.stdout.readline, b""):
                if line.strip() == ready:
                    return bytes(out)
                out += line
            raise RuntimeError("ExifTool exited unexpectedly")


def _key(path: str) -> str:
    return path.replace("\\", "/")  # ExifTool reports Windows paths with forward slashes


def _shot(path: str, row: dict) -> Shot:
    serial = row.get("SerialNumber", row.get("InternalSerialNumber", ""))
    try:
        taken = datetime.strptime(str(row.get("DateTimeOriginal"))[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        taken = None
    try:
        count = int(row.get("ShutterCount", row.get("ImageCount")))
    except (TypeError, ValueError):
        count = None
    return Shot(path, str(row.get("Make", "")), str(row.get("Model", "")), str(serial), taken, count)


def _image(row: dict, tag: str) -> tuple[bytes, int] | None:
    data = row.get(tag)
    if not isinstance(data, str) or not data.startswith("base64:"):
        return None
    return base64.b64decode(data[7:]), _ROTATION.get(row.get("Orientation"), 0)
