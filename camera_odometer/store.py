"""The hidden `.data` folder next to the app: last-used settings and the scan cache, as JSON.

Both files are conveniences. One that cannot be read counts as empty and one that cannot be
written is skipped, so neither can ever block a scan.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    path = app_dir() / ".data"
    path.mkdir(exist_ok=True)
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(path), 2)  # FILE_ATTRIBUTE_HIDDEN
    return path


class Store:
    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory) if directory else data_dir()

    def settings(self) -> dict:
        return self._read("settings.json")

    def save_settings(self, settings: dict) -> None:
        self._write("settings.json", settings)

    def load_cache(self) -> dict:
        return self._read("cache.json")

    def save_cache(self, cache: dict) -> None:
        self._write("cache.json", cache)

    def _read(self, name: str) -> dict:
        try:
            with open(self.dir / name, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}  # missing or corrupt: start empty
        return data if isinstance(data, dict) else {}

    def _write(self, name: str, data: dict) -> None:
        """Atomic: a crash mid-write leaves the previous file intact."""
        tmp = None
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.dir / name)
        except OSError:
            if tmp:
                Path(tmp).unlink(missing_ok=True)
