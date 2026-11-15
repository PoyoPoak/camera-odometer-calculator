"""Engine tests: only the logic that can silently go wrong."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from camera_odometer import calc
from camera_odometer.models import (BUSINESS, PERSONAL, Camera, CameraRange, Folder,
                                    ScanResult, Session, Shot)
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


class StoreTest(unittest.TestCase):
    def test_session_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            self.assertIsNone(store.load_session("/x", 2031))
            session = Session(sample_scan(), {"biz": BUSINESS}, ["Beta 2|0002"])
            store.save_session(session)
            loaded = store.load_session("/x", 2031)
            self.assertEqual(loaded, session)
            self.assertIsNotNone(loaded.saved_at)
            self.assertEqual(store.sessions(), [session])
            self.assertIsNone(store.load_session("/x", 2030))

            store.save_settings({"root": "/x"})
            self.assertEqual(store.settings(), {"root": "/x"})
            next(Path(tmp).glob("session-*.json")).write_text("{not json")
            self.assertIsNone(store.load_session("/x", 2031))
            self.assertEqual(store.sessions(), [])


if __name__ == "__main__":
    unittest.main()
