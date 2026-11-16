"""Entry point and main window: step bar, page stack, the session, and the scan lifecycle."""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import traceback

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import calc
from ..models import Session
from ..store import Store
from . import theme
from .theme import num
from .workers import Engine

STEPS = ("Folder", "Cameras", "Classify", "Results")
STEP_PAGE = ("home", "cameras", "classify", "results")
STEP_OF = {"home": 0, "scanning": 0, "cameras": 1, "classify": 2, "gallery": 2, "results": 3}
BACK = {"cameras": "home", "classify": "cameras", "results": "classify"}


def real_scan(roots, year, engine, store, progress, cancelled):
    """Runs on a worker thread. Returns None when the user cancelled."""
    import errno

    from ..scan import ScanCancelled, scan

    for root in roots:
        if not os.path.isdir(root):
            raise FileNotFoundError(errno.ENOENT, "Folder not found", root)
    cache = store.load_cache()
    try:
        result = scan(roots, year, engine.et(), cache=cache, progress=progress, cancelled=cancelled)
    except ScanCancelled:
        return None
    store.save_cache(cache)
    return result


def real_list_images(folder: str) -> list[str]:
    from ..scan import list_images
    return list_images(folder)


def classified(session: Session) -> tuple[int, int]:
    """(folders with an effective label, folders) - the one definition every page uses."""
    rels = [f.rel for f in session.scan.folders]
    return sum(calc.effective_label(r, session.labels) is not None for r in rels), len(rels)


def root_photos(scan) -> list[tuple[str, int]]:
    """(photo folder, in-year photos inside it) for each folder that was scanned."""
    def norm(p):
        return os.path.normcase(os.path.normpath(p))

    out = []
    for root in scan.roots:
        r = norm(root)
        inside = [f for f in scan.folders if norm(f.path) == r or norm(f.path).startswith(r.rstrip(os.sep) + os.sep)]
        out.append((os.path.normpath(root), sum(rng.frames for f in inside for rng in f.ranges)))
    return out


class StepButton(QPushButton):
    def __init__(self, index: int):
        super().__init__(STEPS[index])
        self.index = index
        self.state = "todo"  # todo | done | current
        self.setFocusPolicy(Qt.NoFocus)
        self.setFlat(True)
        self.setFixedHeight(52)
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance(STEPS[index]) + 56)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        current, done = self.state == "current", self.state == "done"
        hot = done and self.underMouse()
        fg = QColor(theme.TEXT if current or hot else theme.DIM if done else theme.FAINT)
        disc = QRectF(8, (self.height() - 22) / 2, 22, 22)
        p.setPen(Qt.NoPen if current else QPen(fg, 1.2))
        p.setBrush(QColor(theme.TEXT) if current else Qt.NoBrush)
        p.drawEllipse(disc)
        if done:
            p.setPen(QPen(fg, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            c = disc.center()
            p.drawPolyline([c + QPointF(-4.5, 0.5), c + QPointF(-1.2, 3.6), c + QPointF(4.6, -3.4)])
        else:
            f = self.font()
            f.setPixelSize(12)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(theme.BG) if current else fg)
            p.drawText(disc, Qt.AlignCenter, str(self.index + 1))
        f = self.font()
        f.setBold(current)
        p.setFont(f)
        p.setPen(fg)
        p.drawText(self.rect().adjusted(40, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class MainWindow(QMainWindow):
    progress = Signal(int, int, str)  # scan worker -> UI thread

    def __init__(self, store: Store, engine: Engine, scan_fn=real_scan, list_images=real_list_images):
        super().__init__()
        from .classify import ClassifyPage
        from .gallery import GalleryPage
        from .pages import CamerasPage, HomePage, ScanPage
        from .results import ResultsPage

        self.store, self.engine = store, engine
        self.scan_fn, self.list_images = scan_fn, list_images
        self.session: Session | None = None  # in memory only: nothing about it is written to disk
        self.unsaved = False  # labels or exclusions changed since the last export
        self.reached = 0
        self._cancel = threading.Event()

        self.setWindowTitle("Camera Business Use")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        bar = theme.frame("stepbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 0, 24, 0)
        row.setSpacing(0)
        self.step_buttons = []
        for i in range(len(STEPS)):
            if i:
                line = theme.frame("line")
                line.setFixedWidth(28)
                row.addWidget(line)
                row.addSpacing(8)
            b = StepButton(i)
            b.clicked.connect(lambda _=False, i=i: self.go_step(i))
            self.step_buttons.append(b)
            row.addWidget(b)
            row.addSpacing(8)
        row.addStretch(1)
        self.status = theme.label("", "dim")  # short messages only, such as a saved CSV
        row.addWidget(self.status)
        row.addSpacing(12)
        self.folders_button = theme.button("Included Folders  ▾", "menu", focus=False)
        self.folders_menu = QMenu(self.folders_button)
        self.folders_button.setMenu(self.folders_menu)
        row.addWidget(self.folders_button)

        self.stack = QStackedWidget()
        self.pages = {"home": HomePage(self), "scanning": ScanPage(self), "cameras": CamerasPage(self),
                      "classify": ClassifyPage(self), "gallery": GalleryPage(self),
                      "results": ResultsPage(self)}
        for page in self.pages.values():
            page.setObjectName("page")
            page.setAttribute(Qt.WA_StyledBackground, True)
            self.stack.addWidget(page)
        self.progress.connect(self.pages["scanning"].on_progress)

        central = QWidget()
        col = QVBoxLayout(central)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(bar)
        col.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        QApplication.instance().installEventFilter(self)
        self.go("home")

    # -- navigation --

    @property
    def page_name(self) -> str:
        return next(n for n, p in self.pages.items() if p is self.stack.currentWidget())

    def go(self, name: str) -> None:
        step = STEP_OF[name]
        if name != "home":
            self.reached = max(self.reached, step)
        self.stack.setCurrentWidget(self.pages[name])
        for b in self.step_buttons:
            b.state = "current" if b.index == step else "done" if self.can_go(b.index, name) else "todo"
            b.setCursor(Qt.PointingHandCursor if b.state == "done" else Qt.ArrowCursor)
            b.update()
        self.set_status("")
        self._show_folders(name)
        self.pages[name].enter()

    def _show_folders(self, name: str) -> None:
        """The step bar's "Included Folders" list: each scanned photo folder and its photos of the year."""
        shown = self.session is not None and name not in ("home", "scanning")
        self.folders_button.setVisible(shown)
        if shown:
            self.folders_menu.clear()
            for root, photos in root_photos(self.session.scan):
                # A tab puts the count in the menu's right-aligned shortcut column.
                self.folders_menu.addAction(f"{root}\t{num(photos)} photo{'s' if photos != 1 else ''}")

    def can_go(self, step: int, current: str | None = None) -> bool:
        if (current or self.page_name) == "scanning":
            return False
        return step == 0 or (self.session is not None and step <= self.reached)

    def go_step(self, step: int) -> None:
        if self.can_go(step) and STEP_OF[self.page_name] != step:
            self.go(STEP_PAGE[step])

    def back(self) -> None:
        name = self.page_name
        if name == "scanning":
            self.cancel_scan()
        elif name in BACK:
            self.go(BACK[name])

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    # -- scan --

    def start_scan(self, roots: list[str], year: int) -> None:
        settings = self.store.settings()
        settings.update(last_roots=roots, last_year=year)
        self.store.save_settings(settings)
        cancel = self._cancel = threading.Event()
        last = [0.0]

        def progress(done, total, message):
            now = time.monotonic()
            if now - last[0] > 0.03 or done >= total:
                last[0] = now
                self.progress.emit(done, total, message)

        self.pages["scanning"].begin(roots, year)
        self.go("scanning")
        self.engine.run(lambda: self.scan_fn(roots, year, self.engine, self.store, progress, cancel.is_set),
                        lambda result: self._scan_done(result, cancel),
                        lambda message: self._scan_failed(message, cancel))

    def cancel_scan(self) -> None:
        self._cancel.set()
        self.go("home")

    def start_over(self) -> None:
        """Results: drop the session (labels included) and go back to Home for a new scan."""
        if self.confirm_discard("Start over anyway?", "Start Over"):
            self.session, self.reached, self.unsaved = None, 0, False
            self.go("home")

    def _scan_done(self, result, cancel) -> None:
        if cancel.is_set() or result is None:
            return
        # A rescan in the same window keeps the labels of folders that are still there.
        old, self.session = self.session, Session(result)
        if old and old.scan.root == result.root:
            rels = [f.rel for f in result.folders]
            self.session.labels = {rel: label for rel, label in old.labels.items()
                                   if not rel or any(r == rel or r.startswith(rel + "/") for r in rels)}
            self.session.excluded = [cid for cid in old.excluded if cid in {c.id for c in result.cameras}]
        self.reached = 1
        self.go("cameras")

    def _scan_failed(self, message: str, cancel) -> None:
        if not cancel.is_set():
            self.go("home")
            self.pages["home"].show_error(message)

    # -- keys --

    def eventFilter(self, obj, event):
        """Keys go to the current page first, whichever child widget has focus."""
        if (event.type() == QEvent.KeyPress and isinstance(obj, QWidget)
                and (obj is self or self.isAncestorOf(obj))
                and QApplication.activeModalWidget() is None):
            if is_enter(event) and event.isAutoRepeat():
                return True  # a held Enter must not run through Cameras, Classify and Results
            if is_enter(event) and isinstance(obj, QPushButton) and obj.focusPolicy() != Qt.NoFocus:
                obj.click()  # Enter on a focused button presses that button, not the page's default
                return True
            if self.stack.currentWidget().handle_key(event):
                return True
            if event.key() == Qt.Key_Escape:
                self.back()
                return True
        return False

    def needs_confirm(self) -> bool:
        return bool(self.unsaved and self.session and self.session.labels)

    def close_prompt(self, question: str = "Close anyway?", action: str = "Close") -> QMessageBox:
        box = QMessageBox(QMessageBox.Warning, "Camera Business Use", f"Labels are not saved. {question}",
                          QMessageBox.Cancel, self)
        box.setInformativeText("To keep a record, choose Cancel and export the CSV on the Results page.")
        box.addButton(action, QMessageBox.AcceptRole)
        box.setDefaultButton(QMessageBox.Cancel)
        return box

    def confirm_discard(self, question: str, action: str) -> bool:
        """True when no unexported labels would be lost, or the user agrees to lose them."""
        if not self.needs_confirm() or QApplication.platformName() == "offscreen":  # headless runs never wait
            return True
        box = self.close_prompt(question, action)
        box.exec()
        return self.discard_ok(box)

    @staticmethod
    def discard_ok(box: QMessageBox) -> bool:
        """The answer to close_prompt(): its action button, not Cancel, Esc or the title-bar close."""
        return box.buttonRole(box.clickedButton()) == QMessageBox.AcceptRole

    def closeEvent(self, event):
        if not self.confirm_discard("Close anyway?", "Close"):
            event.ignore()
            return
        self._cancel.set()
        self.engine.close()
        super().closeEvent(event)


def is_enter(event) -> bool:
    mods = event.modifiers() & ~Qt.KeypadModifier
    return event.key() in (Qt.Key_Return, Qt.Key_Enter) and mods == Qt.NoModifier


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="camera-business-use", description="Camera Business Use Calculator")
    ap.add_argument("--demo", action="store_true", help="open with an invented photo library")
    ap.add_argument("--screenshots", metavar="DIR", help="dev: save a PNG of every screen and exit")
    ap.add_argument("--selftest", action="store_true", help="dev: check keyboard handling and exit")
    args = ap.parse_args(argv)
    headless = bool(args.screenshots or args.selftest)
    if headless:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"  # never opens a window on the desktop

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Camera Business Use")
    theme.apply(app)
    if headless:
        from . import demo
        return demo.run_headless(app, args.screenshots, args.selftest)
    try:
        if args.demo:
            from . import demo
            window = demo.make_window()
        else:
            window = MainWindow(Store(), Engine())
    except OSError as exc:
        QMessageBox.critical(None, "Camera Business Use", "The app could not create its data folder next to "
                             f"the program ({exc.strerror or exc}). Move the app to a folder you can write to.")
        return 1

    def unexpected(kind, value, tb):  # a bug must be visible, but never as a traceback dialog
        traceback.print_exception(kind, value, tb)
        window.set_status(f"Something went wrong: {value}")

    sys.excepthook = unexpected
    window.show()
    return app.exec()
