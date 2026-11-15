"""Shared data contract between the engine and the UI.

Engine modules (exif, scan, calc, store) and the UI package both import from
here. Nothing in this file may import Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

BUSINESS = "business"
PERSONAL = "personal"


@dataclass(frozen=True)
class Shot:
    """Metadata of one image file, as read by exiftool."""

    path: str
    make: str = ""
    model: str = ""
    serial: str = ""  # SerialNumber, else InternalSerialNumber, else ""
    taken: datetime | None = None  # DateTimeOriginal, naive camera-local time
    shutter_count: int | None = None  # ShutterCount, else ImageCount

    @property
    def camera_id(self) -> str:
        return f"{self.model}|{self.serial}"


def _span(first: Shot, last: Shot, frames: int, estimated: bool) -> int:
    if estimated:
        return frames
    return last.shutter_count - first.shutter_count + 1


@dataclass
class CameraRange:
    """One camera body's in-year span inside one folder."""

    camera_id: str
    first: Shot  # lowest in-year shutter count (earliest shot when estimated)
    last: Shot  # highest in-year shutter count (latest shot when estimated)
    frames: int  # original files this body has in the folder for the year
    estimated: bool = False  # body exposes no shutter count: actuations = frames

    @property
    def actuations(self) -> int:
        return _span(self.first, self.last, self.frames, self.estimated)


@dataclass
class Folder:
    rel: str  # posix path relative to ScanResult.root ("" for that folder itself); absolute when root is ""
    path: str  # absolute path
    ranges: list[CameraRange] = field(default_factory=list)


@dataclass
class Camera:
    """One camera body's odometer for the whole year."""

    id: str
    make: str
    model: str
    serial: str
    first: Shot
    last: Shot
    frames: int
    estimated: bool = False

    @property
    def actuations(self) -> int:
        return _span(self.first, self.last, self.frames, self.estimated)


@dataclass
class ScanResult:
    root: str  # what Folder.rel is relative to: the common parent of `roots`, "" when they share none
    year: int
    cameras: list[Camera] = field(default_factory=list)
    folders: list[Folder] = field(default_factory=list)  # in-year only, sorted by rel
    warnings: list[str] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)  # the selected photo folders; [root] when left empty

    def __post_init__(self) -> None:
        self.roots = self.roots or [self.root]


@dataclass
class Session:
    """Everything persisted for one (root, year) pair."""

    scan: ScanResult
    labels: dict[str, str] = field(default_factory=dict)  # Folder.rel -> BUSINESS | PERSONAL
    excluded: list[str] = field(default_factory=list)  # Camera.id values left out of the math
    saved_at: datetime | None = None


@dataclass
class FolderRow:
    rel: str
    label: str | None  # effective label: own, else nearest labelled ancestor
    raw: int  # sum of range spans, before overlap resolution
    attributed: int  # actuations credited to this folder after overlap resolution


@dataclass
class Overlap:
    camera_id: str
    a: str  # Folder.rel
    b: str  # Folder.rel
    shared: int  # actuations inside both ranges


@dataclass
class Summary:
    year_total: int
    business: int
    personal: int
    unclassified: int  # in folders with no effective label yet
    unattributed: int  # inside the year's range but in no folder (deleted or missing shots)
    rows: list[FolderRow] = field(default_factory=list)
    overlaps: list[Overlap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def business_pct(self) -> float:
        return 100.0 * self.business / self.year_total if self.year_total else 0.0
