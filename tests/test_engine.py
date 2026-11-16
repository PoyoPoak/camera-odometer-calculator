"""Engine tests: only the logic that can silently go wrong."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from camera_odometer import calc, scan
from camera_odometer.models import BUSINESS, PERSONAL, Camera, CameraRange, Folder, ScanResult, Shot
from camera_odometer.store import Store


def shot(name, count=None, model="Alpha 1", serial="0001", taken=datetime(2031, 6, 1)):
    return Shot(name, "Acme", model, serial, taken, count)


def rng(lo, hi, frames=1, **kw):
    first, last = shot("a.raw", lo, **kw), shot("b.raw", hi, **kw)
    return CameraRange(first.camera_id, first, last, frames, estimated=lo is None)


def camera(lo, hi, frames=1, **kw):
    r = rng(lo, hi, frames, **kw)
    return Camera(r.camera_id, "Acme", r.first.model, r.first.serial, r.first, r.last, frames, r.estimated)


def sample_scan():
    phone = dict(model="Phone", serial="")
    other = dict(model="Beta 2", serial="0002")
    folders = [
        Folder("biz/a", "/x/biz/a", [rng(1, 400), rng(None, None, 30, **phone)]),
        Folder("biz/adjacent", "/x/biz/adjacent", [rng(401, 450)]),   # touches a, no overlap
        Folder("c", "/x/c", [rng(350, 380)]),                         # unlabelled, nested in a
        Folder("d", "/x/d", [rng(601, 700), rng(1, 50, **other)]),
        Folder("e", "/x/e", [rng(601, 700), rng(None, None, 12, **phone)]),  # ties with d
        Folder("late", "/x/late", [rng(950, 1100)]),                  # runs past the year range
        Folder("me", "/x/me", [rng(101, 200)]),                       # nested in a
        Folder("me/one", "/x/me/one", [rng(150, 150)]),               # one count, nested twice
    ]
    cameras = [camera(1, 1000, 900), camera(1, 50, 50, **other), camera(None, None, 42, **phone)]
    return ScanResult("/x", 2031, cameras, folders, ["scan warning"])


class CalcTest(unittest.TestCase):
    def test_attribution(self):
        scan = sample_scan()
        labels = {"biz": BUSINESS, "d": BUSINESS, "e": PERSONAL, "me": PERSONAL, "late": BUSINESS}
        s = calc.summarize(scan, labels, excluded=["Beta 2|0002"])

        self.assertEqual(calc.effective_label("biz/a", labels), BUSINESS)
        self.assertIsNone(calc.effective_label("c", labels))
        rows = {r.rel: r for r in s.rows}
        self.assertEqual([r.rel for r in s.rows], [f.rel for f in scan.folders])
        self.assertEqual(rows["biz/a"].label, BUSINESS)
        self.assertEqual(rows["me/one"].label, PERSONAL)
        # a: 400 counts, minus me (100, which includes me/one) and c (31), plus 30 phone files
        self.assertEqual((rows["biz/a"].raw, rows["biz/a"].attributed), (430, 299))
        self.assertEqual(rows["biz/adjacent"].attributed, 50)
        self.assertEqual(rows["c"].attributed, 31)
        self.assertEqual(rows["me"].attributed, 99)
        self.assertEqual(rows["me/one"].attributed, 1)
        # d and e tie: personal wins; d's other body is excluded
        self.assertEqual((rows["d"].raw, rows["d"].attributed), (100, 0))
        self.assertEqual((rows["e"].raw, rows["e"].attributed), (112, 112))
        # late is clipped to the year range 950..1000
        self.assertEqual((rows["late"].raw, rows["late"].attributed), (151, 51))

        self.assertEqual(s.year_total, 1000 + 42)
        self.assertEqual(s.business, 299 + 50 + 51)
        self.assertEqual(s.personal, 99 + 1 + 112)
        self.assertEqual(s.unclassified, 31)
        self.assertEqual(s.unattributed, 150 + 249)  # 451..600 and 701..949
        self.assertEqual(s.business + s.personal + s.unclassified + s.unattributed, s.year_total)

        overlaps = {(o.a, o.b): o.shared for o in s.overlaps}
        self.assertEqual(overlaps, {("biz/a", "c"): 31, ("biz/a", "me"): 100, ("biz/a", "me/one"): 1,
                                    ("d", "e"): 100, ("me", "me/one"): 1})
        self.assertEqual(s.warnings[0], "scan warning")
        self.assertEqual(len(s.warnings), 2)  # plus the estimated phone

    def test_folder_split_into_runs(self):
        # A sparse folder split by the scan into per-day runs of one body; the gap between its
        # runs belongs to the album that covers it, else to nobody.
        folders = [Folder("album", "/x/album", [rng(3000, 3009, 10)]),
                   Folder("keepers", "/x/keepers", [rng(1000, 1001, 2), rng(6000, 6002, 2)]),
                   Folder("touching", "/x/touching", [rng(7000, 7005, 2), rng(7005, 7010, 2)])]
        scan = ScanResult("/x", 2031, [camera(1000, 7010, 18)], folders)
        s = calc.summarize(scan, {"keepers": BUSINESS, "album": PERSONAL})
        rows = {r.rel: r for r in s.rows}
        self.assertEqual((rows["keepers"].raw, rows["keepers"].attributed), (5, 5))
        self.assertEqual((rows["album"].raw, rows["album"].attributed), (10, 10))
        self.assertEqual((rows["touching"].raw, rows["touching"].attributed), (12, 11))
        self.assertEqual((s.business, s.personal, s.unclassified), (5, 10, 11))
        self.assertEqual(s.unattributed, 6011 - 26)
        self.assertEqual(s.business + s.personal + s.unclassified + s.unattributed, s.year_total)
        self.assertEqual(s.overlaps, [])  # runs of one folder never overlap "with each other"
        self.assertEqual(calc.to_csv(scan, s).count("keepers,"), 3)  # one row per run, one credit row


class StoreTest(unittest.TestCase):
    def test_settings_and_cache_survive_bad_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            self.assertEqual((store.settings(), store.load_cache()), ({}, {}))
            store.save_settings({"last_roots": ["/x"], "last_year": 2031})
            store.save_cache({"key": ["Acme", "Alpha 1", "0001", None, 7]})
            self.assertEqual(store.settings(), {"last_roots": ["/x"], "last_year": 2031})
            self.assertEqual(store.load_cache(), {"key": ["Acme", "Alpha 1", "0001", None, 7]})

            (Path(tmp) / "settings.json").write_text("{not json")
            (Path(tmp) / "cache.json").write_text("[1, 2]")
            self.assertEqual((store.settings(), store.load_cache()), ({}, {}))
            store.save_settings({"last_year": 2030})  # a corrupt file is simply replaced
            self.assertEqual(store.settings(), {"last_year": 2030})

            blocked = Store(Path(tmp) / "settings.json" / "sub")  # cannot be created: a file is in the way
            blocked.save_cache({"a": 1})  # must not raise
            self.assertEqual(blocked.load_cache(), {})


class FakeExifTool:
    """Answers read() from a dict and remembers how many files were asked for."""

    def __init__(self):
        self.meta: dict[str, Shot] = {}
        self.files_read = 0

    def read(self, paths):
        self.files_read += len(paths)
        return [self.meta.get(p, Shot(p)) for p in paths]


class ScanTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.et = FakeExifTool()

    def add(self, rel, count=None, taken=datetime(2031, 6, 1), **kw):
        """Create an empty file and tell the fake ExifTool what it holds."""
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        if taken:
            self.et.meta[path] = shot(path, count, taken=taken, **kw)

    def test_plain_group_reads_only_the_ends(self):
        for n in range(1, 11):  # IMG10 must sort after IMG9
            self.add(f"trip/IMG{n}.arw", 99 + n, datetime(2031, 6, 1, 12, n))
        self.add("trip/.IMG0.arw", 1)
        self.add("trip/notes.txt", taken=None)
        cache = {}
        result = scan.scan(self.root, 2031, self.et, cache=cache)

        self.assertEqual(self.et.files_read, 2)
        (folder,), (cam,) = result.folders, result.cameras
        (r,) = folder.ranges
        self.assertEqual((folder.rel, folder.path), ("trip", os.path.join(self.root, "trip")))
        self.assertEqual((r.first.shutter_count, r.last.shutter_count, r.frames, r.actuations), (100, 109, 10, 10))
        self.assertEqual((cam.id, cam.actuations, cam.frames, cam.estimated), ("Alpha 1|0001", 10, 10, False))
        images = scan.list_images(folder.path)
        self.assertEqual([os.path.basename(p) for p in images], [f"IMG{n}.arw" for n in range(1, 11)])

        self.assertEqual(scan.scan(self.root, 2031, self.et, cache=cache), result)
        self.assertEqual(self.et.files_read, 2)  # the rescan came from the cache
        cache[next(iter(cache))] = ["damaged"]
        self.assertEqual(scan.scan(self.root, 2031, self.et, cache=cache), result)
        self.assertEqual(self.et.files_read, 3)  # a damaged cache entry is only a miss

    def test_group_straddling_the_year_is_bisected(self):
        start = datetime(2030, 12, 12)  # 20 files in 2030, 30 in 2031, 14 in 2032
        days = [*range(20), *range(20, 50), *range(400, 414)]
        for n, day in enumerate(days, 1):
            self.add(f"IMG{n:04d}.ARW", n, start + timedelta(days=day))
        result = scan.scan(self.root, 2031, self.et)
        (r,) = result.folders[0].ranges
        self.assertEqual(result.folders[0].rel, "")
        self.assertEqual((r.first.shutter_count, r.last.shutter_count, r.frames), (21, 50, 30))
        self.assertLess(self.et.files_read, 16)  # 2 ends + two bisects of at most 6 probes

        (r,) = scan.scan(self.root, 2032, self.et).folders[0].ranges
        self.assertEqual((r.first.shutter_count, r.last.shutter_count), (51, 64))
        self.assertEqual(scan.scan(self.root, 2029, self.et).folders, [])

    def test_wrapped_file_numbers_are_rotated_without_a_full_read(self):
        # The camera rolled over from IMG9999 to IMG0001, so the newest files sort first.
        numbers = [*range(9990, 10000), *range(1, 31)]
        for i, n in enumerate(numbers):
            self.add(f"IMG{n:04d}.arw", 100 + i, datetime(2031, 6, 1) + timedelta(minutes=i))
        result = scan.scan(self.root, 2031, self.et)
        (r,) = result.folders[0].ranges
        self.assertEqual((r.first.shutter_count, r.last.shutter_count, r.frames), (100, 139, 40))
        self.assertLess(self.et.files_read, 10)  # 2 ends + at most 6 probes for the seam

    def test_identical_ends_hiding_a_wrap_force_a_full_read(self):
        # Shooting order 9998, 9999, 0001, 0002; 9999 and 0001 are one silent-shutter burst.
        for name, count, minute in (("9998", 100, 0), ("9999", 105, 1), ("0001", 105, 1), ("0002", 110, 2)):
            self.add(f"IMG{name}.arw", count, datetime(2031, 6, 1, 12, minute))
        (r,) = scan.scan(self.root, 2031, self.et).folders[0].ranges
        self.assertEqual((r.first.shutter_count, r.last.shutter_count, r.frames), (100, 110, 4))

    def test_two_bodies_in_one_group_are_split_by_full_read(self):
        for n in range(1, 11):
            self.add(f"wed/IMG{n:04d}.arw", 499 + n)
            # second body: its counter moves once per two files
            self.add(f"wed/IMG{n + 10:04d}.arw", 70 + n // 2, model="Beta 2", serial="0002")
        result = scan.scan(self.root, 2031, self.et)
        self.assertEqual(self.et.files_read, 20)
        a, b = result.folders[0].ranges
        self.assertEqual((a.camera_id, a.first.shutter_count, a.last.shutter_count, a.frames),
                         ("Alpha 1|0001", 500, 509, 10))
        self.assertEqual((b.camera_id, b.first.shutter_count, b.last.shutter_count, b.frames),
                         ("Beta 2|0002", 70, 75, 10))
        self.assertEqual([c.id for c in result.cameras], ["Alpha 1|0001", "Beta 2|0002"])
        self.assertEqual(len(result.warnings), 1)  # Beta 2: counter moved 6 for 10 files
        self.assertIn("wed", result.warnings[0])

    def test_sparse_folder_is_split_into_days(self):
        # A catch-all of keepers from two shoots must not claim every count between them.
        for n in range(10):  # a dense album over two days stays one range
            self.add(f"album/IMG{3000 + n}.arw", 3000 + n, datetime(2031, 6, 10 + n // 5, 12, n))
        for count, day in ((1000, 1), (1001, 1), (6000, 20), (6002, 20)):
            self.add(f"keepers/IMG{count}.arw", count, datetime(2031, 6, day, 12, count % 10))
        result = scan.scan(self.root, 2031, self.et)
        album, keepers = result.folders
        self.assertEqual([(r.first.shutter_count, r.last.shutter_count, r.frames) for r in album.ranges],
                         [(3000, 3009, 10)])
        self.assertEqual([(r.camera_id, r.first.shutter_count, r.last.shutter_count, r.frames)
                          for r in keepers.ranges],
                         [("Alpha 1|0001", 1000, 1001, 2), ("Alpha 1|0001", 6000, 6002, 2)])
        (cam,) = result.cameras
        self.assertEqual((cam.first.shutter_count, cam.last.shutter_count, cam.frames), (1000, 6002, 14))
        self.assertEqual(result.warnings, [])

    def test_two_roots_share_one_body(self):
        # One body's year is split over two selected folders. A folder inside another root is no root.
        for n in range(1, 6):
            self.add(f"work/a/IMG{n:04d}.arw", 99 + n)
            self.add(f"archive/b/IMG{n:04d}.arw", 299 + n)
        roots = [os.path.join(self.root, *d.split("/")) for d in ("work", "archive", "work/a")]
        result = scan.scan(roots, 2031, self.et)
        self.assertEqual((result.root, result.roots), (self.root, roots[:2]))
        self.assertEqual([f.rel for f in result.folders], ["archive/b", "work/a"])
        (cam,) = result.cameras
        self.assertEqual((cam.first.shutter_count, cam.last.shutter_count, cam.actuations), (100, 304, 205))

    def test_files_without_counts_are_derivatives_or_estimated(self):
        for n in range(1, 6):
            self.add(f"a/IMG{n:04d}.arw", 199 + n)
            self.add(f"a/IMG{n:04d}.jpg", 199 + n)             # camera JPEG of the same frame
            self.add(f"a/IMG{n:04d}-edit.dng", serial="")      # export: model, no count
            self.add(f"exports/IMG{n:04d}.jpg", serial="")
        for n in range(1, 5):
            self.add(f"phone/PXL{n}.heic", taken=datetime(2031, 3, n), model="Phone", serial="")
        for n in range(3, 7):  # 3 and 4 pair with a .heic, 5 and 6 are frames of their own
            self.add(f"phone/PXL{n}.jpg", taken=datetime(2031, 3, n), model="Phone", serial="")
        for n in range(1, 6):  # originals between two exports that share their prefix
            self.add(f"mix/IMG{n:04d}.jpg", 298 + n if 1 < n < 5 else None, serial="0001" if 1 < n < 5 else "")
        result = scan.scan(self.root, 2031, self.et)

        self.assertEqual([f.rel for f in result.folders], ["a", "mix", "phone"])
        (r,) = result.folders[0].ranges
        self.assertEqual((r.first.shutter_count, r.last.shutter_count, r.frames, r.estimated), (200, 204, 5, False))
        (m,) = result.folders[1].ranges
        self.assertEqual((m.first.shutter_count, m.last.shutter_count, m.frames), (300, 302, 3))
        (p,) = result.folders[2].ranges
        self.assertEqual((p.estimated, p.frames, p.actuations, p.first.taken.day, p.last.taken.day),
                         (True, 6, 6, 1, 6))
        self.assertEqual([(c.model, c.estimated, c.actuations) for c in result.cameras],
                         [("Alpha 1", False, 103), ("Phone", True, 6)])


if __name__ == "__main__":
    unittest.main()
