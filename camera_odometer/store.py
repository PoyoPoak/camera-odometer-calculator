"""JSON persistence in the hidden `.data` folder next to the app."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .models import Camera, CameraRange, Folder, ScanResult, Session, Shot


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
        return self._read_dict("settings.json")

    def save_settings(self, settings: dict) -> None:
        self._write("settings.json", settings)

    def load_cache(self) -> dict:
        return self._read_dict("cache.json")

    def save_cache(self, cache: dict) -> None:
        self._write("cache.json", cache)

    def load_session(self, roots: list[str], year: int) -> Session | None:
        return self._read_session(self.dir / _session_name(roots, year))

    def save_session(self, session: Session) -> None:
        """Stamps `session.saved_at` and writes it."""
        session.saved_at = datetime.now()
        self._write(_session_name(session.scan.roots, session.scan.year), dataclasses.asdict(session))

    def sessions(self) -> list[Session]:
        """Every readable saved session, newest first."""
        found = [s for s in map(self._read_session, self.dir.glob("session-*.json")) if s]
        return sorted(found, key=lambda s: s.saved_at or datetime.min, reverse=True)

    def _read(self, path: Path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _read_dict(self, name: str) -> dict:
        try:
            data = self._read(self.dir / name)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _read_session(self, path: Path) -> Session | None:
        try:
            return _session(self._read(path))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None  # missing, corrupt, or written by an incompatible version

    def _write(self, name: str, data) -> None:
        """Atomic: a crash mid-write leaves the previous file intact."""
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, default=datetime.isoformat)
            os.replace(tmp, self.dir / name)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _session_name(roots: list[str], year: int) -> str:
    """One session per set of photo folders and year, whatever order the folders were picked in."""
    key = "|".join(sorted(os.path.normcase(os.path.normpath(r)) for r in roots)) + f"|{year}"
    return f"session-{hashlib.sha1(key.encode()).hexdigest()[:12]}.json"


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _shot(d: dict) -> Shot:
    return Shot(**{**d, "taken": _dt(d["taken"])})


def _range(d: dict) -> CameraRange:
    return CameraRange(**{**d, "first": _shot(d["first"]), "last": _shot(d["last"])})


def _session(d: dict) -> Session:
    s = d["scan"]
    scan = ScanResult(
        s["root"], s["year"],
        [Camera(**{**c, "first": _shot(c["first"]), "last": _shot(c["last"])}) for c in s["cameras"]],
        [Folder(f["rel"], f["path"], [_range(r) for r in f["ranges"]]) for f in s["folders"]],
        list(s["warnings"]), list(s["roots"]))
    return Session(scan, dict(d["labels"]), list(d["excluded"]), _dt(d["saved_at"]))
