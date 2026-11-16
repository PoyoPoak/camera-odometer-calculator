"""Smart scan: each folder's shutter-count ranges from a few probed files.

See docs/architecture.md for the algorithm.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import datetime

from .models import Camera, CameraRange, Folder, ScanResult, Shot

RAW_EXTS = frozenset(".arw .cr2 .cr3 .nef .nrw .raf .orf .rw2 .pef .dng .srw .x3f .3fr .iiq "
                     ".rwl .erf .sr2 .srf".split())
IMAGE_EXTS = RAW_EXTS | {".jpg", ".jpeg", ".heic"}

_CHUNK = 50  # files per exiftool call, so progress can advance


class ScanCancelled(Exception):
    pass


class _Mixed(Exception):
    """A group is not one body's ordered run; all of it must be read."""


def list_images(folder: str) -> list[str]:
    folder = os.path.abspath(folder)
    return [os.path.join(folder, name) for name in _scandir(folder)[0]]


def scan(roots: str | list[str], year: int, et, *,
         cache: dict | None = None,
         progress: Callable[[int, int, str], None] | None = None,
         cancelled: Callable[[], bool] | None = None) -> ScanResult:
    """Scan one photo folder or several as one library. See _select for how rels are formed."""
    root, roots, root_rels = _select(roots)
    warnings: list[str] = []
    reader = _Reader(et, {} if cache is None else cache, progress, cancelled)
    reader.report("Listing folders")

    # 1-2. Walk, and group each folder's images by (prefix, extension).
    paths: dict[str, str] = {}
    groups: list[tuple[str, list[str]]] = []  # (folder rel, one (prefix, extension) group in natural order)
    for start in zip(root_rels, roots):
        for rel, path, names in _walk(*start, warnings):
            reader.check_cancelled()
            paths[rel] = path
            by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
            for name in names:
                stem, ext = os.path.splitext(name)
                by_key[re.match(r"\D*", stem).group(), ext.lower()].append(os.path.join(path, name))
            groups += [(rel, files) for files in by_key.values()]

    # 3. Probe both ends of every group, batched.
    ends = list(dict.fromkeys(p for _, files in groups for p in (files[0], files[-1])))
    probe = dict(zip(ends, reader.read(ends)))

    # 4. Resolve each group into runs of (first, last, frames) per body. Groups with counts go
    # first, so that count-less copies of a counted model are dropped without reading more.
    runs: dict[tuple[str, str], list[tuple[Shot, Shot, list[str]]]] = defaultdict(list)

    def no_counts(group) -> bool:
        return probe[group[1][0]].shutter_count is None and probe[group[1][-1]].shutter_count is None

    for group in sorted(groups, key=no_counts):
        rel, files = group
        a, b = probe[files[0]], probe[files[-1]]
        if no_counts(group) and {a.model, b.model} <= reader.counted_models | {""}:
            # Derivatives, or not camera files at all, unless originals sit between two of them.
            # ponytail: one probe in the middle; counted files hidden behind count-less ends AND
            # a count-less middle are still missed. Probe more of the group if that ever bites.
            if len(files) < 3 or reader.read([files[len(files) // 2]])[0].shutter_count is None:
                continue
            found = _split(reader.read(files), year)
        else:
            found = _resolve(files, a, b, year, reader)
        for run in found:
            runs[rel, run[0].camera_id].append(run)

    # 5. One CameraRange per (folder, body), one Camera per body.
    folders: dict[str, Folder] = {}
    by_body: dict[str, list[CameraRange]] = defaultdict(list)
    for (rel, camera_id), found in sorted(runs.items()):
        counted = [r for r in found if r[0].shutter_count is not None]
        if not counted and found[0][0].model in reader.counted_models:
            continue  # derivative
        key = _count if counted else _taken
        # A raw + JPEG pair shares its file name and is one frame.
        stems = {os.path.splitext(os.path.basename(p))[0].lower() for r in counted or found for p in r[2]}
        rng = CameraRange(camera_id,
                          min((r[0] for r in counted or found), key=key),
                          max((r[1] for r in counted or found), key=key),
                          len(stems), estimated=not counted)
        folders.setdefault(rel, Folder(rel, paths[rel])).ranges.append(rng)
        by_body[camera_id].append(rng)
        if counted and rng.actuations < 0.9 * rng.frames:
            warnings.append(f"{rel or 'Top folder'}: the {rng.first.model} counter moved {rng.actuations:,} "
                            f"but the folder holds {rng.frames:,} files (electronic shutter?).")

    cameras = []
    for camera_id, ranges in sorted(by_body.items()):
        key = _taken if ranges[0].estimated else _count
        first = min((r.first for r in ranges), key=key)
        last = max((r.last for r in ranges), key=key)
        cameras.append(Camera(camera_id, first.make, first.model, first.serial, first, last,
                              sum(r.frames for r in ranges), ranges[0].estimated))
    reader.report("Done")
    return ScanResult(root, year, cameras, [folders[rel] for rel in sorted(folders)], warnings, roots)


def _inside(path: str, parent: str) -> bool:
    try:
        return os.path.normcase(os.path.commonpath([path, parent])) == os.path.normcase(parent)
    except ValueError:  # different drives
        return False


def _select(roots: str | list[str]) -> tuple[str, list[str], list[str]]:
    """(common parent, roots, each root's rel). A root inside another selected root is dropped.

    One root is its own parent (rel ""). Roots on different drives have no parent: the parent
    is "" and every rel is an absolute path with "/" separators.
    """
    paths = [os.path.abspath(p) for p in ([roots] if isinstance(roots, str) else roots)]
    paths = list({os.path.normcase(p): p for p in paths}.values())
    roots = [p for p in paths if not any(q != p and _inside(p, q) for q in paths)]
    if len(roots) == 1:
        return roots[0], roots, [""]
    try:
        parent = os.path.commonpath(roots)
    except ValueError:  # different drives, or no roots at all
        return "", roots, [p.replace("\\", "/") for p in roots]
    return parent, roots, [os.path.relpath(p, parent).replace(os.sep, "/") for p in roots]


def _count(shot: Shot) -> int:
    return shot.shutter_count


def _taken(shot: Shot) -> datetime:
    return shot.taken


def _natural(name: str) -> list:
    # re.split with a group alternates text, digits, text, ...
    return [int(t) if i % 2 else t.lower() for i, t in enumerate(re.split(r"(\d+)", name))]


def _scandir(folder: str) -> tuple[list[str], list[str]]:
    """(image file names in natural order, sub-folder names), hidden and system entries skipped."""
    files, dirs = [], []
    with os.scandir(folder) as entries:
        for e in entries:
            if e.name.startswith("."):
                continue
            is_dir = e.is_dir(follow_symlinks=False)
            # Windows: skip hidden (2) entries and system (4) files. A folder with a custom icon
            # carries the system bit, so folders are only skipped when hidden. DirEntry.stat is free there.
            if os.name == "nt" and e.stat(follow_symlinks=False).st_file_attributes & (2 if is_dir else 6):
                continue
            if is_dir:
                dirs.append(e.name)
            elif os.path.splitext(e.name)[1].lower() in IMAGE_EXTS:
                files.append(e.name)
    return sorted(files, key=_natural), sorted(dirs, key=_natural)


def _walk(root_rel: str, root: str, warnings: list[str]) -> Iterator[tuple[str, str, list[str]]]:
    """(rel, path, image names) for every folder under root that holds images. No file is opened."""
    stack = [(root_rel, root)]
    while stack:
        rel, path = stack.pop()
        try:
            files, dirs = _scandir(path)
        except OSError as exc:
            if path == root:
                raise  # a selected folder itself is unreadable: the caller's problem
            warnings.append(f"{rel}: could not be read ({exc.strerror or exc}).")
            continue
        if files:
            yield rel, path, files
        stack += [(f"{rel}/{d}" if rel else d, os.path.join(path, d)) for d in reversed(dirs)]


class _Reader:
    """exiftool reads through the cache, with progress and cancellation."""

    def __init__(self, et, cache: dict, progress, cancelled):
        self.et, self.cache, self.progress, self.cancelled = et, cache, progress, cancelled
        self.done = self.total = 0
        self.counted_models: set[str] = set()  # models seen with a shutter count in this scan

    def report(self, message: str) -> None:
        if self.progress:
            self.progress(self.done, self.total, message)

    def check_cancelled(self) -> None:
        if self.cancelled and self.cancelled():
            raise ScanCancelled

    def read(self, paths: list[str]) -> list[Shot]:
        keys = {p: _cache_key(p) for p in paths}
        shots = {p: _load(p, self.cache[k]) for p, k in keys.items() if k in self.cache}
        shots = {p: s for p, s in shots.items() if s}
        todo = [p for p in paths if p not in shots]
        self.total += len(paths)
        self.done += len(paths) - len(todo)
        for i in range(0, len(todo), _CHUNK):
            self.check_cancelled()
            chunk = todo[i:i + _CHUNK]
            self.report(os.path.basename(os.path.dirname(chunk[0])))
            for s in self.et.read(chunk):
                shots[s.path] = s
                if keys[s.path] and (s.model or s.taken):  # never cache a failed read
                    self.cache[keys[s.path]] = _dump(s)
            self.done += len(chunk)
        self.counted_models.update(s.model for s in shots.values() if s.shutter_count is not None)
        return [shots[p] for p in paths]


def _cache_key(path: str) -> str:
    try:
        st = os.stat(path)
    except OSError:
        return ""
    return f"{path}|{st.st_size}|{st.st_mtime_ns}"


def _dump(s: Shot) -> list:
    return [s.make, s.model, s.serial, s.taken.isoformat() if s.taken else None, s.shutter_count]


def _load(path: str, v: list) -> Shot | None:
    """The cached Shot, or None for an entry that is damaged or from another version (a cache miss)."""
    try:
        make, model, serial, taken, count = v
        if not all(isinstance(x, str) for x in (make, model, serial)) or not isinstance(count, int | None):
            return None
        return Shot(path, make, model, serial, datetime.fromisoformat(taken) if taken else None, count)
    except (TypeError, ValueError):
        return None


def _ordered(a: Shot, b: Shot) -> bool:
    """Could a and b be an earlier and a later frame of one body's run?"""
    return bool(a.model and a.camera_id == b.camera_id
                and a.taken and b.taken and a.taken <= b.taken
                and (a.shutter_count is None) == (b.shutter_count is None)
                and (a.shutter_count is None or a.shutter_count <= b.shutter_count))


def _bisect(files, lo: int, hi: int, a: Shot, b: Shot, after, reader: _Reader):
    """Narrow lo..hi (shots a..b) to the adjacent pair where `after` turns true."""
    while hi - lo > 1:
        mid = (lo + hi) // 2
        (s,) = reader.read([files[mid]])
        if not (_ordered(a, s) and _ordered(s, b)):
            raise _Mixed
        if after(s):
            hi, b = mid, s
        else:
            lo, a = mid, s
    return lo, a, hi, b


def _unwrap(files: list[str], a: Shot, b: Shot, reader: _Reader) -> tuple[list[str], Shot, Shot]:
    """The file numbers rolled over (9999 -> 0001), so the newest files sort first.

    Find the seam and return the group rotated back into shooting order, with its true ends.
    """
    lo, hi = 0, len(files) - 1  # files[lo] is in the newer part, files[hi] in the older part
    while hi - lo > 1:
        mid = (lo + hi) // 2
        (s,) = reader.read([files[mid]])
        newer, older = _ordered(a, s), _ordered(s, b)
        if newer == older:
            raise _Mixed
        if newer:
            lo, a = mid, s
        else:
            hi, b = mid, s
    return files[hi:] + files[:hi], b, a


def _resolve(files: list[str], a: Shot, b: Shot, year: int, reader: _Reader) -> list[tuple[Shot, Shot, list[str]]]:
    """The in-year runs (first, last, files) of one group, given its probed ends a and b."""
    try:
        if _ordered(b, a):
            if _ordered(a, b) and len(files) > 2:
                raise _Mixed  # identical ends say nothing about the order of what lies between
            if not _ordered(a, b):
                files, a, b = _unwrap(files, a, b, reader)
        if not _ordered(a, b):
            raise _Mixed
        if b.taken.year < year or a.taken.year > year:
            return []
        i, j = 0, len(files) - 1
        if a.taken.year < year:
            _, _, i, a = _bisect(files, i, j, a, b, lambda s: s.taken.year >= year, reader)
            if a.taken.year > year:
                return []
        if b.taken.year > year:
            j, b, _, _ = _bisect(files, i, j, a, b, lambda s: s.taken.year > year, reader)
        return [(a, b, files[i:j + 1])]
    except _Mixed:
        return _split(reader.read(files), year)


def _split(shots: list[Shot], year: int) -> list[tuple[Shot, Shot, list[str]]]:
    """Full-read fallback: one run per body among the in-year shots."""
    bodies: dict[str, list[Shot]] = defaultdict(list)
    for s in shots:
        if s.model and s.taken and s.taken.year == year:
            bodies[s.camera_id].append(s)
    runs = []
    for body in bodies.values():
        counted = [s for s in body if s.shutter_count is not None]
        key = _count if counted else _taken
        body = counted or body  # count-less files of a counted body are derivatives
        runs.append((min(body, key=key), max(body, key=key), [s.path for s in body]))
    return runs


if __name__ == "__main__":
    import sys
    import time

    from .calc import summarize
    from .exif import ExifTool
    from .store import Store

    class _Counting:
        """Counts the files that really reach exiftool (cache misses)."""

        def __init__(self, et):
            self.et, self.files = et, 0

        def read(self, paths):
            self.files += len(paths)
            return self.et.read(paths)

    def _line(first: Shot, last: Shot) -> str:
        return (f"#{first.shutter_count}..#{last.shutter_count}  "
                f"{first.taken:%Y-%m-%d}..{last.taken:%Y-%m-%d}")

    if len(sys.argv) < 3:
        sys.exit("usage: python3 -m camera_odometer.scan YEAR FOLDER [FOLDER ...]")
    _year, _roots = int(sys.argv[1]), sys.argv[2:]
    _store = Store()
    _cache = _store.load_cache()
    _, _kept, _rels = _select(_roots)
    _seen = sum(len(names) for _start in zip(_rels, _kept) for _, _, names in _walk(*_start, []))
    _start = time.monotonic()
    with ExifTool() as _et:
        _counting = _Counting(_et)
        _result = scan(_roots, _year, _counting, cache=_cache,
                       progress=lambda d, t, m: print(f"\r{d}/{t} {m[:40]:40}", end="", file=sys.stderr))
    _elapsed = time.monotonic() - _start
    _store.save_cache(_cache)
    print(file=sys.stderr)
    print("Cameras")
    for c in _result.cameras:
        print(f"  {c.make} {c.model}  serial {'*' * max(len(c.serial) - 3, 0)}{c.serial[-3:]}  "
              f"{_line(c.first, c.last)}  actuations {c.actuations}  frames {c.frames}"
              f"{'  (estimated)' if c.estimated else ''}")
    print("Folders")
    for f in _result.folders:
        for r in f.ranges:
            print(f"  {f.rel or '.'}  [{r.first.model}]  {_line(r.first, r.last)}  "
                  f"actuations {r.actuations}  frames {r.frames}")
    print("Warnings")
    for w in _result.warnings:
        print(f"  {w}")
    _sum = summarize(_result, {})
    print(f"Year total {_sum.year_total:,}: {_sum.unclassified:,} inside folders, "
          f"{_sum.unattributed:,} outside any folder")
    print(f"{_counting.files:,} files read of {_seen:,} seen, {len(_result.folders)} folders, {_elapsed:.1f} s")
