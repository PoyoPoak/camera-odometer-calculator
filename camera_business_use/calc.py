"""Business-use attribution. See docs/calculation.md."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Iterable
from pathlib import PurePath

from .models import BUSINESS, PERSONAL, FolderRow, Overlap, ScanResult, Summary

_TIE_ORDER = {PERSONAL: 0, None: 1, BUSINESS: 2}  # ties go to Personal, then to the conservative side


def effective_label(rel: str, labels: dict[str, str]) -> str | None:
    """The folder's own label, else the nearest labelled ancestor's (the root is "")."""
    while True:
        if rel in labels:
            return labels[rel]
        if not rel:
            return None
        rel = rel.rpartition("/")[0]


def summarize(scan: ScanResult, labels: dict[str, str], excluded: Iterable[str] = ()) -> Summary:
    excluded = set(excluded)
    label = {f.rel: effective_label(f.rel, labels) for f in scan.folders}
    raw: dict[str, int] = defaultdict(int)
    credit: dict[str, int] = defaultdict(int)
    year_total = unattributed = 0
    overlaps: list[Overlap] = []
    warnings = list(scan.warnings)

    for cam in scan.cameras:
        if cam.id in excluded:
            continue
        year_total += cam.actuations
        ranges = [(f.rel, r) for f in scan.folders for r in f.ranges if r.camera_id == cam.id]
        for rel, r in ranges:
            raw[rel] += r.actuations
        if cam.estimated:
            warnings.append(f"{cam.make} {cam.model}".strip() + f" has no shutter count: "
                            f"its {cam.frames:,} files are counted as actuations (estimated).")
            for rel, r in ranges:
                credit[rel] += r.frames
            unattributed += cam.frames - sum(r.frames for _, r in ranges)
            continue

        # Folder ranges clipped to the year range, as half-open (rel, lo, hi).
        lo0, hi0 = cam.first.shutter_count, cam.last.shutter_count + 1
        spans = [(rel, max(r.first.shutter_count, lo0), min(r.last.shutter_count + 1, hi0))
                 for rel, r in ranges]
        spans = [s for s in spans if s[1] < s[2]]
        for i, (a, alo, ahi) in enumerate(spans):
            for b, blo, bhi in spans[i + 1:]:
                if a != b and min(ahi, bhi) > max(alo, blo):  # a folder's own runs are no overlap
                    overlaps.append(Overlap(cam.id, a, b, min(ahi, bhi) - max(alo, blo)))

        # Sweep the segments between endpoints: the narrowest covering range wins each one.
        # ponytail: O(segments x ranges) per body, switch to a heap sweep if a library has thousands of folders
        points = sorted({lo0, hi0, *(p for s in spans for p in s[1:])})
        for a, b in zip(points, points[1:]):
            covering = [s for s in spans if s[1] <= a and b <= s[2]]
            if covering:
                rel = min(covering, key=lambda s: (s[2] - s[1], _TIE_ORDER.get(label[s[0]], 1), s[0]))[0]
                credit[rel] += b - a
            else:
                unattributed += b - a

    rows = [FolderRow(f.rel, label[f.rel], raw[f.rel], credit[f.rel]) for f in scan.folders]
    return Summary(
        year_total=year_total,
        business=sum(r.attributed for r in rows if r.label == BUSINESS),
        personal=sum(r.attributed for r in rows if r.label == PERSONAL),
        unclassified=sum(r.attributed for r in rows if r.label not in (BUSINESS, PERSONAL)),
        unattributed=unattributed,
        rows=rows, overlaps=overlaps, warnings=warnings)


def to_csv(scan: ScanResult, summary: Summary, excluded: Iterable[str] = ()) -> str:
    """The breakdown for tax records. Pass the same `excluded` as to summarize()."""
    excluded = set(excluded)
    cams = {c.id: c for c in scan.cameras}
    label = {r.rel: r.label or "" for r in summary.rows}
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["Folder", "Label", "Camera", "Serial", "First file", "First count",
                "Last file", "Last count", "Raw actuations"])
    for f in scan.folders:
        for r in f.ranges:
            if r.camera_id in excluded:
                continue
            cam = cams.get(r.camera_id)
            w.writerow([f.rel or ".", label.get(f.rel, ""),
                        f"{cam.make} {cam.model}".strip() if cam else r.first.model,
                        r.first.serial, PurePath(r.first.path).name, _blank(r.first.shutter_count),
                        PurePath(r.last.path).name, _blank(r.last.shutter_count), r.actuations])
    w.writerow([])
    w.writerow(["Folder", "Label", "Credited actuations"])
    for row in summary.rows:
        w.writerow([row.rel or ".", row.label or "", row.attributed])
    w.writerow([])
    w.writerow(["Year total", summary.year_total])
    w.writerow(["Business", summary.business])
    w.writerow(["Personal", summary.personal])
    w.writerow(["Unclassified", summary.unclassified])
    w.writerow(["Unattributed", summary.unattributed])
    w.writerow(["Business %", f"{summary.business_pct:.1f}"])
    return out.getvalue()


def _blank(value: int | None) -> int | str:
    return "" if value is None else value
