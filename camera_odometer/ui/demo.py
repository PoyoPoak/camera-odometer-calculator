"""Invented library for --demo, plus the headless --screenshots and --selftest runs."""
from __future__ import annotations

import os
import random
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QEvent, QIODevice, QPointF, Qt
from PySide6.QtGui import (QColor, QImage, QKeyEvent, QLinearGradient, QPainter, QRadialGradient,
                           QTransform)
from PySide6.QtWidgets import QApplication, QPushButton

from ..models import BUSINESS, PERSONAL, Camera, CameraRange, Folder, ScanResult, Session, Shot
from ..store import Store
from . import theme

YEAR = datetime.now().year - 1
ROOT = "D:/Photos"  # common parent of the two demo photo folders
ROOTS = ("Library", "Studio")

_A = ("SONY", "ILCE-7CM2", "04417358")
_B = ("SONY", "ILCE-7M4", "03902117")
_DRONE = ("DJI", "FC3582", "")

# rel, [(body, first count, last count, frames, (month, day), (month, day))]
_FOLDERS = [
    ("Library/01-18 Winter Lakeshore", [(_A, 14210, 14890, 601, (1, 18), (1, 18))]),
    ("Library/02-08 Studio Headshots", [(_A, 14900, 15720, 780, (2, 8), (2, 8)),
                                (_B, 9920, 10310, 377, (2, 8), (2, 8))]),
    ("Library/03-14 Harbor Portraits", [(_A, 15730, 16480, 702, (3, 14), (3, 15))]),
    ("Library/04-05 Spring Trail Hike", [(_A, 16490, 16912, 365, (4, 5), (4, 5))]),
    ("Library/04-26 Riverside Marathon", [(_A, 16920, 17400, 455, (4, 26), (4, 26))]),
    ("Library/04-26 Riverside Marathon/Course", [(_B, 10320, 11100, 744, (4, 26), (4, 26))]),
    ("Library/04-26 Riverside Marathon/Finish Line", [(_A, 17401, 18250, 812, (4, 26), (4, 26))]),
    ("Library/05-17 Aerial Vineyard", [(_DRONE, None, None, 232, (5, 17), (5, 17))]),
    ("Library/07-19 Coastal Road Trip", [(_A, 20960, 22400, 1198, (7, 19), (8, 2)),
                                 (_DRONE, None, None, 180, (7, 20), (8, 1))]),
    ("Library/07-26 Lighthouse Engagement", [(_A, 21500, 21790, 268, (7, 26), (7, 26))]),
    ("Library/10-31 Costume Party", [(_A, 23700, 24105, 371, (10, 31), (10, 31))]),
    ("Library/11-08 Silent Recital", [(_B, 12110, 12480, 640, (11, 8), (11, 8))]),
    ("Library/Portfolio Selects", [(_A, 14893, 14895, 3, (1, 27), (1, 27)),  # sparse: one run per day
                                   (_A, 18260, 18261, 2, (5, 30), (5, 30)),
                                   (_A, 22450, 22452, 3, (8, 20), (8, 20))]),
    ("Studio/06-21 Garden Wedding", [(_A, 18300, 20950, 2410, (6, 20), (6, 21)),
                                      (_B, 11110, 12100, 905, (6, 21), (6, 21))]),
    ("Studio/09-12 Product Catalog", [(_A, 22600, 23650, 988, (9, 12), (9, 13))]),
]

DEMO_LABELS = {
    "Library/01-18 Winter Lakeshore": PERSONAL,
    "Library/02-08 Studio Headshots": BUSINESS,
    "Library/03-14 Harbor Portraits": BUSINESS,
    "Library/04-26 Riverside Marathon": BUSINESS,  # its two sub-folders inherit
    "Library/07-19 Coastal Road Trip": PERSONAL,
    "Studio/06-21 Garden Wedding": BUSINESS,
}


def demo_scan(root: str = ROOT, year: int = YEAR) -> ScanResult:
    def shot(body, rel, count, md, name):
        make, model, serial = body
        return Shot(f"{root}/{rel}/{name}", make, model, serial,
                    datetime(year, md[0], md[1], 10, 30), count)

    folders, per_body = [], {}
    for rel, ranges in _FOLDERS:
        out = []
        for body, lo, hi, frames, d0, d1 in ranges:
            est = lo is None
            ext = "DNG" if est else "ARW"
            first = shot(body, rel, lo, d0, f"DSC{(lo or 1) % 100000:05d}.{ext}")
            last = shot(body, rel, hi, d1, f"DSC{(hi or frames) % 100000:05d}.{ext}")
            r = CameraRange(first.camera_id, first, last, frames, est)
            out.append(r)
            per_body.setdefault(first.camera_id, []).append(r)
        folders.append(Folder(rel, f"{root}/{rel}", out))
    cameras = []
    for cid, ranges in per_body.items():
        est = ranges[0].estimated
        key = (lambda s: s.taken) if est else (lambda s: s.shutter_count)
        first = min((r.first for r in ranges), key=key)
        last = max((r.last for r in ranges), key=key)
        cameras.append(Camera(cid, first.make, first.model, first.serial, first, last,
                              sum(r.frames for r in ranges), est))
    warnings = ["Library/11-08 Silent Recital: the counter moved 371 but the folder holds 640 files "
                "(electronic shutter?)."]
    return ScanResult(root, year, cameras, sorted(folders, key=lambda f: f.rel), warnings,
                      [f"{root}/{name}" for name in ROOTS])


def fake_scan(roots, year, engine, store, progress, cancelled):
    """Stands in for the real scan in demo mode: same signature as app.real_scan."""
    result = demo_scan(ROOT, year)
    total = 618
    for done in range(total + 1):
        if cancelled():
            return None
        progress(done, total, result.folders[done * len(result.folders) // (total + 1)].rel)
        time.sleep(0.004)
    return result


def list_images(folder: str) -> list[str]:
    posix = folder.replace("\\", "/")
    count = sum(sum(r[3] for r in ranges) for name, ranges in _FOLDERS if posix.endswith("/" + name))
    return [f"{folder}/DSC{n:05d}.ARW" for n in range(1, count + 1)]


def _jpeg(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPEG", 88)
    return bytes(data)


def _portrait(path: str) -> bool:
    return random.Random(path + "/orientation").random() < 0.15


def _painted(path: str, w: int, h: int) -> tuple[bytes, int]:
    """A gradient "photograph" and its rotation, stable per path, hue shared by the folder."""
    if _portrait(path):  # stored sideways like a camera would, with rotation 90 to stand it up
        w, h = h, w
    rnd = random.Random(path)
    hue = (random.Random(os.path.dirname(path)).random() + rnd.uniform(-0.05, 0.05)) % 1
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    sky = QLinearGradient(0, 0, w * rnd.uniform(0, 0.5), h)
    sky.setColorAt(0, QColor.fromHsvF(hue, 0.35, rnd.uniform(0.55, 0.8)))
    sky.setColorAt(1, QColor.fromHsvF((hue + 0.1) % 1, 0.55, 0.22))
    p.fillRect(img.rect(), sky)
    for _ in range(3):
        c = QPointF(rnd.uniform(0, w), rnd.uniform(0, h * 0.7))
        radius = rnd.uniform(0.15, 0.4) * w
        glow = QRadialGradient(c, radius)
        glow.setColorAt(0, QColor.fromHsvF((hue + rnd.uniform(0, 0.15)) % 1, 0.25, 1.0, 0.5))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(glow)
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, radius, radius)
    ground = QLinearGradient(0, h * 0.62, 0, h)
    ground.setColorAt(0, QColor.fromHsvF((hue + 0.5) % 1, 0.3, 0.2, 0.9))
    ground.setColorAt(1, QColor.fromHsvF((hue + 0.5) % 1, 0.35, 0.07))
    horizon = h * rnd.uniform(0.6, 0.78)
    p.fillRect(0, int(horizon), w, h, ground)
    p.end()
    if _portrait(path):
        return _jpeg(img.transformed(QTransform().rotate(-90))), 90
    return _jpeg(img), 0


class DemoExifTool:
    """Same surface as exif.ExifTool, backed by painted images instead of files."""

    alive = True

    def read(self, paths):
        out = []
        for p in paths:
            count = None if "export" in os.path.basename(p).lower() else 18_342
            out.append(Shot(p, "SONY", "ILCE-7CM2", "04417358", datetime(YEAR, 6, 21, 16, 42), count))
        return out

    def thumbnails(self, paths):
        return {p: _painted(p, 320, 213) for p in paths}

    def preview(self, path):
        return _painted(path, 1620, 1080)

    def close(self, wait: float = 0):
        pass


def make_window(data: Path | None = None):
    """A MainWindow wired to the invented library and a throwaway data folder."""
    from .app import MainWindow
    from .workers import Engine

    store = Store(data or Path(tempfile.mkdtemp(prefix="camera-odometer-demo-")))
    store.save_settings({"last_roots": [f"{ROOT}/{name}".replace("/", "\\") for name in ROOTS],
                         "last_year": YEAR})
    return MainWindow(store, Engine(DemoExifTool), scan_fn=fake_scan, list_images=list_images)


def _open(win, session: Session) -> None:
    """Headless runs: straight to Classify, as if this session had just been scanned."""
    win.session, win.reached = session, 3 if session.labels else 2
    win.go("classify")


# ---- headless runs: --screenshots and --selftest ---------------------------

def _settle(win, timeout: float = 15.0) -> None:
    """Pump events until workers, timers and the flash animation are all idle."""
    classify, gallery = win.pages["classify"], win.pages["gallery"]
    deadline, quiet = time.monotonic() + timeout, 0
    while quiet < 3:
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QApplication.processEvents()
        busy = (win.engine.pending or classify._strip_timer.isActive() or gallery._lazy.isActive()
                or gallery._preview_timer.isActive()
                or classify.anim.state() == classify.anim.State.Running or win.page_name == "scanning")
        quiet = 0 if busy else quiet + 1
        if time.monotonic() > deadline:
            raise AssertionError("the UI did not become idle")
        time.sleep(0.005)


def _key(target, key, mods=Qt.NoModifier) -> None:
    QApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, key, mods))
    QApplication.sendEvent(target, QKeyEvent(QEvent.KeyRelease, key, mods))


def _selftest(win) -> int:
    from ..calc import effective_label

    checks = 0

    def check(cond, what):
        nonlocal checks
        if not cond:
            raise AssertionError(what)
        checks += 1

    page = win.pages["classify"]
    tree = page.tree
    buttons = {b.property("kind"): b for b in page.findChildren(QPushButton)}
    session = Session(demo_scan())
    labels = session.labels
    _open(win, session)
    _settle(win)
    first, second, third, fourth = (f.rel for f in session.scan.folders[:4])
    parent, child = "Library/04-26 Riverside Marathon", "Library/04-26 Riverside Marathon/Course"

    check(win.page_name == "classify" and page.current == first, "Classify opens on the first folder")
    _key(tree, Qt.Key_Down)
    check(page.current == second, "Down moves to the next folder")
    _key(tree.viewport(), Qt.Key_Up)
    check(page.current == first, "Up moves to the previous folder")

    _key(tree, Qt.Key_Right)
    check(labels.get(first) == BUSINESS, "Right marks Business (focus on the tree)")
    check(page.current == first, "the selection waits for the flash")
    check(buttons["business"].property("on") == "own" and buttons["personal"].property("on") == "",
          "the folder's own label lights its Business button")
    _settle(win)
    check(page.current == second, "after the flash the selection jumps to the next unclassified folder")

    _key(buttons["personal"], Qt.Key_Left)
    check(labels.get(second) == PERSONAL, "Left marks Personal (key sent to the Personal button)")
    _settle(win)
    check(page.current == third, "jumped again")
    buttons["business"].click()
    _settle(win)
    check(labels.get(third) == BUSINESS and page.current == fourth, "a click on Business equals Right")
    del labels[third]
    page._select(third)

    _key(page, Qt.Key_Right)
    _key(page, Qt.Key_Left)  # pressed during the flash: belongs to the next folder
    check(labels.get(third) == BUSINESS and labels.get(fourth) == PERSONAL,
          "a key pressed during the flash applies to the next folder")
    _settle(win)
    check(page.current == parent, "landed on the folder with sub-folders")

    check(page.items[parent].isExpanded(), "sub-folders start expanded")
    _key(tree, Qt.Key_Left)
    check(labels.get(parent) == PERSONAL and page.items[parent].isExpanded(),
          "Left labels a folder with sub-folders instead of collapsing it")
    _settle(win)
    page.items[parent].setExpanded(False)
    page._select(parent)
    _key(tree, Qt.Key_Right)
    check(labels.get(parent) == BUSINESS and not page.items[parent].isExpanded(),
          "Right labels a collapsed folder instead of expanding it")
    check(child not in labels and effective_label(child, labels) == BUSINESS,
          "sub-folders inherit the parent's label")
    page._select(child)
    check(buttons["business"].property("on") == "inherited" and not page.inherited.isHidden(),
          "an inherited label is shown as inherited")
    page._select(parent)
    _settle(win)
    check(page.current == "Library/05-17 Aerial Vineyard", "the jump skips folders that inherited a label")
    page.items[parent].setExpanded(True)

    page._select(parent)
    _key(tree, Qt.Key_Space)
    _settle(win)
    check(win.page_name == "gallery" and page.items[parent].isExpanded(),
          "Space opens the gallery instead of collapsing the folder")
    _key(win, Qt.Key_Escape)
    check(win.page_name == "classify" and page.current == parent, "Esc from the gallery lands on the folder")

    page._select(first)
    before = page.done.text()
    _key(tree, Qt.Key_Backspace)
    check(first not in labels and page.current == first and page.done.text() != before,
          "Backspace clears the label and stays put")

    last = session.scan.folders[-1].rel
    for f in session.scan.folders:
        if f.rel not in (first, last):
            labels.setdefault(f.rel, PERSONAL)
    page._refresh()
    page._select(last)
    _key(tree, Qt.Key_Left)
    _settle(win)
    check(page.current == first, "the jump wraps around once")
    _key(tree, Qt.Key_Right)
    _settle(win)
    n = len(session.scan.folders)
    check(page.current == first and page.done.text() == f"{n} / {n}", "nothing left: stay put, all counted")

    check(win.needs_confirm(), "closing with labels that were not exported asks first")
    win.go("results")
    win.pages["results"].copy_summary()
    check(not win.needs_confirm(), "after an export or a copied summary, closing does not ask")
    win.go("classify")
    _key(tree, Qt.Key_Left)
    check(win.needs_confirm(), "a label changed after the export asks again")
    _settle(win)

    labels.clear()
    page._refresh()
    page._select("Studio")
    _key(tree, Qt.Key_Right)
    check(labels == {"Studio": BUSINESS}
          and effective_label("Studio/06-21 Garden Wedding", labels) == BUSINESS,
          "a folder without shots of its own can be classified and passes its label down")
    _settle(win)

    _key(tree, Qt.Key_Return)
    check(win.page_name == "results", "Enter opens Results")
    _key(win.pages["results"].table, Qt.Key_Escape)
    check(win.page_name == "classify", "Esc goes back to Classify")
    page._select(third)
    _key(tree, Qt.Key_Space)
    _settle(win)
    gallery = win.pages["gallery"]
    check(win.page_name == "gallery" and gallery.model.rowCount() > 0, "Space opens the gallery")
    _key(gallery.grid, Qt.Key_Return)
    check(gallery.stack.currentWidget() is gallery.viewer, "Enter opens the single image")
    _key(gallery.grid, Qt.Key_Right)
    check(gallery.row == 1, "Right flips to the next image")
    _settle(win)
    _key(gallery.grid, Qt.Key_Escape)
    check(win.page_name == "gallery" and gallery.stack.currentIndex() == 0, "Esc returns to the grid")
    _key(gallery.grid, Qt.Key_P)
    check(win.page_name == "classify" and labels.get(third) == PERSONAL, "P classifies from the gallery")
    _settle(win)
    _key(tree, Qt.Key_Escape)
    check(win.page_name == "cameras", "Esc goes back to Cameras")
    back = next(b for b in win.pages["cameras"].findChildren(QPushButton) if b.text() == "Back")
    _key(back, Qt.Key_Return)
    check(win.page_name == "home", "Enter on a focused button presses that button")
    win.go("cameras")
    QApplication.sendEvent(win.pages["cameras"].next,
                           QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "", True))
    check(win.page_name == "cameras", "a held (auto-repeated) Enter does nothing")
    _key(win.pages["cameras"].next, Qt.Key_Return)
    check(win.page_name == "classify", "Enter on Cameras continues")

    page._select("Studio/06-21 Garden Wedding")
    strip, total = page.strip, len(list_images(page.folders[page.current].path))
    sizes = []
    for size in ((1280, 800), (1800, 700), (1100, 900)):
        win.resize(*size)
        _settle(win)
        sizes.append(strip.capacity(total))
        cols, rows, w, h = strip._grid(total)
        check(len(strip.images) == cols * rows and all(i is not None for i in strip.images)
              and strip.height() - rows * (h + 8) < h, f"previews fill the space at {size[0]}x{size[1]}")
    check(len(set(sizes)) == 3, f"the number of previews follows the window size {sizes}")
    win.resize(1280, 800)

    win.go("home")
    home = win.pages["home"]
    check(len(home.roots) == 2, "Home remembers the photo folders used last")
    home.path.setText('"E:\\More Photos"')
    _key(home.path, Qt.Key_Return)
    check(win.page_name == "home" and home.roots[-1] == "E:\\More Photos" and not home.path.text(),
          "Enter adds a typed folder to the list instead of scanning")
    _settle(win)
    _key([b for b in home.findChildren(QPushButton) if b.text() == "Remove"][-1], Qt.Key_Return)
    check(len(home.roots) == 2, "Enter on a focused Remove button removes that folder")
    _settle(win)
    check(not QApplication.windowIcon().pixmap(32).isNull(), "the window icon loads from assets/icon.ico")

    from .pages import CheckDialog
    dialog = CheckDialog(win)
    dialog.load("D:/Photos/Library/folder.ico")
    check("not a photo" in dialog.note.text() and not win.engine.pending, "a non-photo file is refused unread")
    dialog.deleteLater()

    dead = win.engine.et()
    dead.alive = False
    check(win.engine.et() is not dead, "an ExifTool whose process died is replaced on the next use")

    bar = win.pages["scanning"].bar
    win.pages["scanning"].begin(home.roots, YEAR)
    win.pages["scanning"].on_progress(50, 100, "")
    half = bar.value()
    win.pages["scanning"].on_progress(50, 400, "")  # a fallback read added 300 files
    check(half == bar.value() == 500, "the scan bar does not move backwards when the total grows")

    _key(home.path, Qt.Key_Return)
    check(win.page_name == "scanning", "Enter on Home starts the scan")
    _key(win, Qt.Key_Escape)
    check(win.page_name == "home", "Esc cancels the scan")
    _settle(win)
    _key(home.path, Qt.Key_Enter)
    _settle(win)
    check(win.page_name == "cameras", "a finished scan opens Cameras")
    check(win.session.labels == labels and win.session is not session,
          "a rescan in the same window keeps the labels")

    photos = {name: sum(r[3] for rel, ranges in _FOLDERS if rel.startswith(name + "/") for r in ranges)
              for name in ROOTS}
    check([a.text() for a in win.folders_menu.actions()]
          == [f"{os.path.normpath(f'{ROOT}/{n}')}\t{photos[n]:,} photos" for n in ROOTS]
          and not win.folders_button.isHidden(), "Included Folders lists each photo folder and its photos")
    win.go("results")
    win.start_over()
    check(win.page_name == "home" and win.session is None and not win.can_go(1)
          and win.folders_button.isHidden(), "Start Over drops the session and returns Home")
    return checks + _selftest_pages(win) + _selftest_viewer(win)


def _selftest_pages(win) -> int:
    """Home, Scan, Cameras and Check Shutter Count. Sets up the state it needs."""
    return 0


def _selftest_viewer(win) -> int:
    """Gallery, single-image view and Results. Sets up the state it needs."""
    from PySide6.QtGui import QMouseEvent

    checks = 0

    def check(cond, what):
        nonlocal checks
        if not cond:
            raise AssertionError(what)
        checks += 1

    press, release, move = QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove
    click = (press, release)

    def mouse(widget, pos, *kinds):
        for kind in kinds:
            button = Qt.NoButton if kind == move else Qt.LeftButton
            held = Qt.LeftButton if kind in (press, QEvent.MouseButtonDblClick) else Qt.NoButton
            QApplication.sendEvent(widget, QMouseEvent(kind, pos, widget.mapToGlobal(pos), button, held,
                                                       Qt.NoModifier))

    classify, gallery, results = win.pages["classify"], win.pages["gallery"], win.pages["results"]
    viewer = gallery.viewer

    def at(fraction):  # a point on the viewer, that fraction of its width from the left
        return QPointF(viewer.width() * fraction, viewer.height() / 2)

    _open(win, Session(demo_scan(), dict(DEMO_LABELS)))
    classify._select("Library/Portfolio Selects")
    classify.open_gallery()
    _settle(win)
    check(gallery.grid_keys.isVisible() and not gallery.image_keys.isVisible(), "the grid shows its hotkeys")
    gallery.open_image()
    check(gallery.image_keys.isVisible() and not gallery.grid_keys.isVisible(),
          "the single image swaps in its own hotkeys")

    mouse(viewer, at(0.1), move, *click)
    check(gallery.row == 0 and viewer.hover == -1 and not viewer.bar(),
          "the first image has no bar on its left, and a click there does nothing")
    mouse(viewer, at(0.9), move)
    check(viewer.bar() == 1 and viewer.cursor().shape() == Qt.PointingHandCursor,
          "the right third shows a bar and a pointing hand")
    mouse(viewer, at(0.9), *click)
    check(gallery.row == 1, "a click on the right third flips forward")
    mouse(viewer, at(0.5), move, *click)
    check(gallery.row == 1 and not viewer.bar() and viewer.cursor().shape() == Qt.ArrowCursor,
          "the middle third shows no bar and a click there does nothing")
    mouse(viewer, at(0.1), move, *click)
    check(gallery.row == 0, "a click on the left third flips back")
    # A synthetic press never moves the focus, so check the policy that keeps a real one from doing so.
    check(viewer.focusPolicy() == Qt.NoFocus, "a click on the image does not take the keyboard focus")
    _key(gallery.grid, Qt.Key_Right)
    check(gallery.row == 1, "keys still flip after a click")
    last = gallery.model.rowCount() - 1
    gallery.flip(last - 1 - gallery.row)
    mouse(viewer, at(0.9), move, *click)
    check(gallery.row == last and not viewer.bar() and viewer.cursor().shape() == Qt.ArrowCursor,
          "a click flips onto the last image, whose bar and hand go at once")
    mouse(viewer, at(0.9), *click)
    check(gallery.row == last, "no flip past the last image")
    mouse(viewer, at(0.1), move)
    QApplication.sendEvent(viewer, QEvent(QEvent.Leave))
    check(viewer.hover == 0 and not viewer.bar(), "leaving the viewer clears the bar")
    _settle(win)

    win.go("results")
    table = results.table
    table.sortByColumn(3, Qt.DescendingOrder)
    row = 1
    rel = table.item(row, 0).toolTip()
    check(rel != results.summary.rows[row].rel, "sorted: the table row is not the summary row")
    mouse(table.viewport(), QPointF(table.visualRect(table.model().index(row, 1)).center()),
          *click, QEvent.MouseButtonDblClick, release)
    _settle(win)
    check(win.page_name == "gallery" and gallery.rel == rel and classify.current == rel,
          "a double-click on a Results row opens that folder's photos")
    _key(gallery.grid, Qt.Key_Escape)
    check(win.page_name == "classify" and classify.current == rel, "Esc then lands on that folder in Classify")

    win.go("results")
    start = next((b for b in results.findChildren(QPushButton) if b.text() == "Start Over"), None)
    check(start is not None, "Results has a Start Over button")
    start.click()
    check(win.page_name == "home" and win.session is None, "Start Over on Results returns Home")
    return checks


def _screenshots(win, out: Path) -> int:
    from .pages import CheckDialog

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    count = 0

    def grab(name, widget=None):
        nonlocal count
        _settle(win)
        for suffix, size in (("", (1280, 800)), ("-min", (1100, 700))):
            if widget is None:
                win.resize(*size)
                _settle(win)
            elif suffix:
                continue
            if not (widget or win).grab().save(str(out / f"{name}{suffix}.png")):
                raise AssertionError(f"could not write {name}{suffix}.png")
            count += 1
        win.resize(1280, 800)

    home, classify, gallery = win.pages["home"], win.pages["classify"], win.pages["gallery"]
    grab("01-home")
    home.show_error("That folder could not be found. Check that the drive is connected and try again.")
    grab("02-home-error")
    home.show_error("")

    win.pages["scanning"].begin(demo_scan().roots, YEAR)
    win.stack.setCurrentWidget(win.pages["scanning"])
    win.pages["scanning"].on_progress(412, 618, "Studio/06-21 Garden Wedding")
    QApplication.processEvents()
    for suffix, size in (("", (1280, 800)), ("-min", (1100, 700))):
        win.resize(*size)
        QApplication.processEvents()
        win.grab().save(str(out / f"03-scan{suffix}.png"))
        count += 1
    win.resize(1280, 800)

    win.session = Session(ScanResult(ROOT, YEAR, roots=demo_scan().roots))
    win.reached = 1
    win.go("cameras")
    grab("04-cameras-empty")
    _open(win, Session(demo_scan(), dict(DEMO_LABELS)))
    win.go("cameras")
    grab("05-cameras")
    boxes = win.pages["cameras"].findChildren(theme.Check)
    boxes[-1].setChecked(False)
    grab("05b-cameras-excluded")
    boxes[-1].setChecked(True)

    labels = win.session.labels
    win.go("classify")
    grab("06-classify")
    classify._select("Studio/06-21 Garden Wedding")
    grab("06b-classify-two-cameras")
    win.resize(1800, 700)  # wide and short: the previews must still fill the space
    _settle(win)
    win.grab().save(str(out / "06d-classify-wide.png"))
    count += 1
    win.resize(1280, 800)
    classify._select("Library/Portfolio Selects")
    grab("06c-classify-days")
    classify._select("Library/04-26 Riverside Marathon/Course")
    grab("07-classify-inherited")
    classify._select("Studio")
    grab("08-classify-parent")
    classify._select("Library/04-05 Spring Trail Hike")
    _settle(win)
    classify.mark(BUSINESS)
    classify.anim.setCurrentTime(120)
    classify.anim.pause()  # freeze mid-flash
    QApplication.processEvents()
    win.grab().save(str(out / "09-classify-flash.png"))
    count += 1
    classify.anim.resume()
    _settle(win)
    keep = dict(labels)
    for f in win.session.scan.folders:
        labels.setdefault(f.rel, PERSONAL)
    classify._refresh()
    grab("10-classify-all-done")
    labels.clear()
    labels.update(keep)
    del labels["Library/04-05 Spring Trail Hike"]
    classify._refresh()

    classify._select("Library/03-14 Harbor Portraits")
    classify.open_gallery()
    grab("11-gallery")
    gallery.grid.setCurrentIndex(gallery.model.index(5))
    gallery.open_image()
    grab("12-image")
    gallery.step_back()
    gallery.step_back()
    classify._select("Studio")
    classify.open_gallery()
    grab("13-gallery-empty")
    gallery.step_back()

    win.go("results")
    grab("14-results")
    win.folders_menu.popup(win.folders_button.mapToGlobal(win.folders_button.rect().bottomLeft()))
    grab("14b-included-folders", win.folders_menu)
    win.folders_menu.close()

    dialog = CheckDialog(win)
    dialog.show()
    grab("15-check", dialog)
    dialog.load("D:/Photos/Library/03-14 Harbor Portraits/DSC15730.ARW")
    grab("16-check-count", dialog)
    dialog.load("D:/Photos/Exports/harbor-portraits-export-012.jpg")
    grab("17-check-no-count", dialog)
    dialog.close()
    prompt = win.close_prompt()  # shown, never exec()ed: a headless run must not wait for an answer
    prompt.show()
    grab("18-close-prompt", prompt)
    prompt.close()
    _shots_pages(win, grab)
    _shots_viewer(win, grab)
    win.go("home")
    return count


def _shots_pages(win, grab) -> None:
    """Extra screenshots of Home, Scan, Cameras and Check Shutter Count: grab(name[, widget])."""


def _shots_viewer(win, grab) -> None:
    """Extra screenshots of Gallery, the single-image view and Results: grab(name[, widget])."""
    classify, gallery = win.pages["classify"], win.pages["gallery"]
    _open(win, Session(demo_scan(), dict(DEMO_LABELS)))
    classify._select("Library/03-14 Harbor Portraits")
    classify.open_gallery()
    _settle(win)
    gallery.grid.setCurrentIndex(gallery.model.index(5))
    gallery.open_image()
    gallery.viewer.hover = 1  # offscreen has no mouse: set the hovered third directly
    grab("12b-image-hover")
    gallery.flip(-5)
    gallery.viewer.hover = -1  # the first image: nothing to flip back to, so no bar
    grab("12c-image-first-hover")
    gallery.viewer.hover = 0
    gallery.step_back()
    gallery.step_back()


def _real_exiftool(scratch: Path) -> int:
    """The ExifTool this app would really use must start and read a file. Returns the width it read."""
    from ..exif import ExifTool

    path = str(scratch / "probe.jpg")
    image = QImage(8, 6, QImage.Format_RGB32)
    image.fill(QColor("#808080"))
    image.save(path)
    with ExifTool() as et:
        widths = [row.get("ImageWidth") for row in et._json(["-ImageWidth"], [path]).values()]
    if widths != [8]:
        raise AssertionError(f"ExifTool did not read the test image (got {widths})")
    return widths[0]


def run_headless(app, shots_dir: str | None, selftest: bool) -> int:
    """Offscreen only. Any exception in a slot or event handler makes the run fail."""
    import threading
    import traceback

    failures = []

    def hook(kind, value, tb):
        traceback.print_exception(kind, value, tb)
        failures.append(value)

    sys.excepthook = hook
    watchdog = threading.Timer(180, lambda: os._exit(3))  # e.g. a dialog waiting for input
    watchdog.daemon = True
    watchdog.start()

    runs = [(_selftest, "selftest: {} checks passed")] * selftest
    if shots_dir:
        runs.append((lambda w: _screenshots(w, Path(shots_dir)), f"screenshots: {{}} PNGs in {shots_dir}"))
    scratch = Path(tempfile.mkdtemp(prefix="camera-odometer-"))  # nothing is left next to the app
    if selftest and getattr(sys, "frozen", False):  # the demo ExifTool above cannot catch a broken bundle
        runs.append((lambda _win: _real_exiftool(scratch),
                     "selftest: the bundled ExifTool read a test image {} pixels wide"))
    for i, (run, message) in enumerate(runs):  # each on a fresh window and data folder
        win = make_window(scratch / f"data-{i}")
        win.show()
        try:
            print(message.format(run(win)))
            _settle(win)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            failures.append(exc)
        win.close()
    shutil.rmtree(scratch, ignore_errors=True)
    watchdog.cancel()
    if failures:
        print(f"FAILED: {len(failures)} error(s)")
        return 1
    return 0
