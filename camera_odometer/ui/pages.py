"""Home, Scan and Cameras pages, and the Check Shutter Count dialog."""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QProgressBar,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..scan import IMAGE_EXTS
from . import theme
from .app import is_enter
from .theme import button, label, num

IMAGE_FILTER = f"Photos ({' '.join('*' + ext for ext in sorted(IMAGE_EXTS))})"


def _column(page: QWidget, width: int) -> QVBoxLayout:
    """A centred column of fixed maximum width inside the page."""
    outer = QHBoxLayout(page)
    outer.setContentsMargins(40, 0, 40, 0)
    holder = QWidget()
    holder.setMaximumWidth(width)
    outer.addStretch(1)
    outer.addWidget(holder, 100)
    outer.addStretch(1)
    col = QVBoxLayout(holder)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(0)
    return col


class HomePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        col = _column(self, 680)
        col.addStretch(2)
        col.addWidget(label("Camera Odometer", "h1"))
        col.addSpacing(6)
        col.addWidget(label("Find out how much of your camera use was for business.", "dim"))
        col.addSpacing(32)

        col.addWidget(label("PHOTO FOLDERS", "caps"))
        col.addSpacing(8)
        self.roots: list[str] = []
        self.root_rows = QVBoxLayout()
        self.root_rows.setSpacing(6)
        col.addLayout(self.root_rows)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.path = QLineEdit()
        self.path.textEdited.connect(lambda: self.show_error(""))
        row.addWidget(self.path, 1)
        row.addWidget(button("Add folder…", on_click=self.browse))
        col.addLayout(row)
        col.addSpacing(20)

        col.addWidget(label("TAX YEAR", "caps"))
        col.addSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.year = QSpinBox()
        self.year.setRange(1990, datetime.now().year)
        self.year.setValue(datetime.now().year - 1)
        self.year.setAlignment(Qt.AlignCenter)
        self.year.setFixedWidth(84)
        for text, step, at in (("−", self.year.stepDown, 0), ("+", self.year.stepUp, 2)):
            b = button(text, "stepper", step, focus=False)
            b.setFixedWidth(38)
            row.insertWidget(at, b)
            if at == 0:
                row.addWidget(self.year)
        row.addStretch(1)
        self.scan_button = button("Scan", "primary", self.scan)
        self.scan_button.setMinimumWidth(140)
        row.addWidget(label("Enter", "faint"))
        row.addSpacing(6)
        row.addWidget(self.scan_button)
        col.addLayout(row)

        self.error = label("", "error", wrap=True)
        self.error.hide()
        col.addSpacing(16)
        col.addWidget(self.error)
        col.addSpacing(20)

        row = QHBoxLayout()
        row.addWidget(button("Check shutter count…", on_click=self.check))
        row.addStretch(1)
        col.addLayout(row)
        col.addStretch(3)

        settings = win.store.settings()
        last = settings.get("last_roots")
        self.roots = [r for r in last if isinstance(r, str)] if isinstance(last, list) else []
        self._show_roots()
        if isinstance(settings.get("last_year"), int):
            self.year.setValue(settings["last_year"])

    def enter(self):
        self.path.setFocus()

    def handle_key(self, event) -> bool:
        if is_enter(event):
            if self.path.text().strip():
                self.add(self.path.text())  # Enter adds a typed folder; Enter again scans
            else:
                self.scan()
            return True
        return False

    def show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(bool(message))

    def _show_roots(self) -> None:
        while self.root_rows.count():
            self.root_rows.takeAt(0).widget().deleteLater()
        for root in self.roots:
            w = theme.frame("folder")
            row = QHBoxLayout(w)
            row.setContentsMargins(12, 2, 2, 2)
            name = label(root)
            name.setMinimumWidth(40)
            name.setToolTip(root)
            row.addWidget(name, 1)
            remove = button("Remove", "ghost", lambda root=root: self.remove(root))
            remove.setAccessibleName(f"Remove {root}")
            row.addWidget(remove)
            self.root_rows.addWidget(w)
        self.root_rows.setContentsMargins(0, 0, 0, 6 if self.roots else 0)
        self.path.setPlaceholderText("Paste another folder path and press Enter" if self.roots else
                                     "Paste the path of a folder that holds your photos, or choose Add folder…")

    def add(self, path: str) -> None:
        path = path.strip().strip('"')
        if path:
            path = os.path.normpath(path)
            if os.path.normcase(path) not in map(os.path.normcase, self.roots):
                self.roots.append(path)
                self._show_roots()
        self.path.clear()
        self.show_error("")

    def remove(self, root: str) -> None:
        self.roots.remove(root)
        self._show_roots()
        self.path.setFocus()

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Add a photo folder", self.roots[-1] if self.roots else "")
        if folder:
            self.add(folder)

    def scan(self):
        self.add(self.path.text())
        if not self.roots:
            self.show_error("Add a photo folder first.")
            self.path.setFocus()
            return
        self.win.start_scan(list(self.roots), self.year.value())

    def check(self):
        CheckDialog(self.win).exec()


class ScanPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        col = _column(self, 560)
        col.addStretch(4)
        self.title = label("", "h2")
        col.addWidget(self.title)
        col.addSpacing(6)
        self.root = label("", "dim")
        col.addWidget(self.root)
        col.addSpacing(28)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        col.addWidget(self.bar)
        col.addSpacing(14)
        row = QHBoxLayout()
        self.message = label("", "dim")
        self.message.setMinimumWidth(40)
        self.counts = label("", "dim", align=Qt.AlignRight)
        row.addWidget(self.message, 1)
        row.addWidget(self.counts)
        col.addLayout(row)
        col.addSpacing(32)
        row = QHBoxLayout()
        row.addWidget(button("Cancel", on_click=win.cancel_scan))
        row.addSpacing(8)
        row.addWidget(label("Esc", "faint"))
        row.addStretch(1)
        col.addLayout(row)
        col.addStretch(5)

    def begin(self, roots: list[str], year: int) -> None:
        self.title.setText(f"Scanning for photos taken in {year}")
        self.root.setText("\n".join(os.path.normpath(r) for r in roots))
        self.bar.setRange(0, 0)  # busy until the first progress report
        self._fraction = 0.0
        self.message.setText("Looking through folders…")
        self.counts.setText("")

    def on_progress(self, done: int, total: int, message: str) -> None:
        # The total grows when a folder needs more reads; the bar never moves backwards for that.
        self._fraction = max(self._fraction, done / total if total else 0.0)
        self.bar.setRange(0, 1000)
        self.bar.setValue(round(1000 * self._fraction))
        self.message.setText(self.message.fontMetrics().elidedText(message, Qt.ElideMiddle, 340))
        self.counts.setText(f"{num(done)} of {num(total)} files read" if total else "")

    def enter(self):
        pass

    def handle_key(self, event) -> bool:
        return False  # Esc is handled by the window: it cancels


class CamerasPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.body = body = QVBoxLayout()
        body.setContentsMargins(40, 32, 40, 0)
        body.addStretch(0)  # grows only for the empty state, to centre it
        self.title = label("", "h2")
        body.addWidget(self.title)
        body.addSpacing(6)
        self.subtitle = label("", "dim", wrap=True)
        body.addWidget(self.subtitle)
        body.addSpacing(24)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_host)
        scroll.setFocusPolicy(Qt.NoFocus)
        body.addWidget(scroll, 1)
        outer.addLayout(body, 1)

        bar = theme.frame("bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(40, 16, 40, 16)
        totals = QVBoxLayout()
        totals.setSpacing(0)
        self.total = label("", "num")
        self.total_note = label("", "caps")
        totals.addWidget(self.total)
        totals.addWidget(self.total_note)
        row.addLayout(totals)
        row.addStretch(1)
        row.addWidget(button("Back", "ghost", win.back))
        row.addSpacing(8)
        row.addWidget(label("Enter", "faint"))
        row.addSpacing(6)
        self.next = button("Continue", "primary", self.proceed)
        self.next.setMinimumWidth(140)
        row.addWidget(self.next)
        outer.addWidget(bar)

    def enter(self):
        s = self.win.session
        scan = s.scan
        while self.grid.count():
            self.grid.takeAt(0).widget().deleteLater()
        self.win.set_status(f"{theme.library_name(scan)} · {scan.year}")
        if not scan.cameras:
            self.title.setText(f"No photos from {scan.year} were found")
            self.subtitle.setText(
                "The scan looks for original camera files (raw files, or JPEGs straight from the camera) "
                f"taken in {scan.year}. Check that you picked the right folders and tax year, then scan again.")
        else:
            n = len(scan.cameras)
            self.title.setText(f"{n} camera{'s' if n != 1 else ''} used in {scan.year}")
            self.subtitle.setText("Each camera's shutter counter works like an odometer: last shot of the year "
                                  "minus first. Untick any camera that should not count, such as a friend's.")
        for text in (self.title, self.subtitle):
            text.setAlignment(Qt.AlignLeft if scan.cameras else Qt.AlignHCenter)
        self.body.setStretch(0, 0 if scan.cameras else 2)
        self.body.setStretch(self.body.count() - 1, 1 if scan.cameras else 3)
        cols = min(3, max(1, len(scan.cameras)))
        for i, cam in enumerate(scan.cameras):
            self.grid.addWidget(self._card(cam), i // cols, i % cols)
        for c in range(3):
            self.grid.setColumnStretch(c, 1 if c < cols or len(scan.cameras) < 3 else 0)
        self.grid.setRowStretch(len(scan.cameras) // cols + 1, 1)
        self._refresh_total()
        self.next.setFocus()

    def _card(self, cam) -> QWidget:
        card = theme.frame("card")
        col = QVBoxLayout(card)
        col.setContentsMargins(22, 20, 22, 18)
        col.setSpacing(0)
        head = QHBoxLayout()
        name = label(theme.camera_name(cam.make, cam.model))
        head.addWidget(name, 1)
        if cam.estimated:
            badge = label("Estimated from file count", "badge")
            badge.setToolTip("This camera does not record a shutter count, so each file counts as one actuation.")
            head.addWidget(badge)
        col.addLayout(head)
        col.addSpacing(2)
        col.addWidget(label(f"Serial {cam.serial}" if cam.serial else "No serial number", "faint"))
        col.addSpacing(20)
        col.addWidget(label(num(cam.actuations), "num"))
        col.addWidget(label("FILES THIS YEAR" if cam.estimated else "YEAR ACTUATIONS", "caps"))
        col.addSpacing(20)
        ends = QGridLayout()
        ends.setHorizontalSpacing(16)
        ends.setVerticalSpacing(4)
        for c, (title, shot) in enumerate((("FIRST SHOT", cam.first), ("LAST SHOT", cam.last))):
            text = theme.short_date(shot.taken)
            if shot.shutter_count is not None:
                text += f" · #{num(shot.shutter_count)}"
            ends.addWidget(label(title, "caps"), 0, c)
            ends.addWidget(label(text), 1, c)
        col.addLayout(ends)
        col.addStretch(1)
        col.addSpacing(18)
        col.addWidget(theme.frame("line"))
        col.addSpacing(14)
        check = theme.Check("Include in calculation")
        check.setCursor(Qt.PointingHandCursor)
        check.setMinimumHeight(24)
        check.setChecked(cam.id not in self.win.session.excluded)

        def shade(on: bool) -> None:  # an excluded camera's card and name are dimmed
            theme.restyle(card, off=not on)
            name.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {theme.TEXT if on else theme.FAINT};")

        shade(check.isChecked())
        check.toggled.connect(lambda on, cid=cam.id: self._toggle(cid, on, shade))
        col.addWidget(check)
        return card

    def _toggle(self, cam_id: str, on: bool, shade) -> None:
        excluded = self.win.session.excluded
        if on and cam_id in excluded:
            excluded.remove(cam_id)
        elif not on and cam_id not in excluded:
            excluded.append(cam_id)
        shade(on)
        self.win.unsaved = True
        self._refresh_total()

    def _refresh_total(self):
        s = self.win.session
        included = [c for c in s.scan.cameras if c.id not in s.excluded]
        self.total.setText(num(sum(c.actuations for c in included)))
        n = len(included)
        self.total_note.setText(f"TOTAL ACTUATIONS · {n} CAMERA{'S' if n != 1 else ''} INCLUDED")
        self.next.setEnabled(bool(included))

    def proceed(self):
        if self.next.isEnabled():
            self.win.go("classify")

    def handle_key(self, event) -> bool:
        if is_enter(event):
            self.proceed()
            return True
        return False


class CheckDialog(QDialog):
    """Shutter count of one image: drop it in or browse to it."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self._token = 0
        self.setWindowTitle("Check Shutter Count")
        self.setModal(True)
        self.setFixedSize(520, 500)
        self.setAcceptDrops(True)
        col = QVBoxLayout(self)
        col.setContentsMargins(28, 24, 28, 22)
        col.setSpacing(0)
        col.addWidget(label("Check shutter count", "h2"))
        col.addSpacing(4)
        col.addWidget(label("See how many shots a camera had taken when it made one image.", "dim", wrap=True))
        col.addSpacing(18)

        self.drop = theme.frame("drop")
        box = QVBoxLayout(self.drop)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(2)
        self.big = label("", "hero", align=Qt.AlignCenter)
        self.big.setStyleSheet("font-size: 64px;")
        self.caption = label("", "caps", align=Qt.AlignCenter)
        self.note = label("", "dim", wrap=True, align=Qt.AlignCenter)
        box.addStretch(1)
        box.addWidget(self.big)
        box.addWidget(self.caption)
        box.addSpacing(8)
        box.addWidget(self.note)
        box.addStretch(1)
        col.addWidget(self.drop, 1)
        col.addSpacing(16)

        self.details = QGridLayout()
        self.details.setHorizontalSpacing(20)
        self.details.setVerticalSpacing(6)
        self.values = {}
        for r, key in enumerate(("File", "Camera", "Serial", "Captured")):
            self.details.addWidget(label(key.upper(), "caps"), r, 0)
            self.values[key] = label("—")
            self.values[key].setMinimumWidth(40)
            self.details.addWidget(self.values[key], r, 1)
        self.details.setColumnStretch(1, 1)
        col.addLayout(self.details)
        col.addSpacing(20)
        row = QHBoxLayout()
        row.addWidget(button("Browse…", "primary", self.browse))
        row.addStretch(1)
        row.addWidget(button("Close", on_click=self.accept))
        col.addLayout(row)
        self._idle()

    def _show(self, big: str, caption: str, note: str) -> None:
        self.big.setText(big)
        self.big.setVisible(bool(big))
        self.caption.setText(caption)
        self.caption.setVisible(bool(caption))
        self.note.setText(note)
        self.note.setVisible(bool(note))

    def _idle(self):
        self._show("", "", "Drop an image here, or choose Browse.")

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose an image", "", IMAGE_FILTER)
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        self._token += 1
        token = self._token
        for v in self.values.values():
            v.setText("—")
        self.values["File"].setText(os.path.basename(path))
        if os.path.splitext(path)[1].lower() not in IMAGE_EXTS:  # ExifTool reads far more than photos
            self._show("", "", "This is not a photo file. Choose a raw file or a JPEG straight from the camera.")
            return
        self._show("", "", "Reading…")
        self.win.engine.run(lambda: self.win.engine.et().read([path]),
                            lambda shots: token == self._token and self._loaded(shots),
                            lambda message: token == self._token and self._show("", "", message))

    def _loaded(self, shots) -> None:
        shot = shots[0] if shots else None
        if shot is None or not (shot.model or shot.taken or shot.shutter_count is not None):
            self._show("", "", "This file could not be read as a photo.")
            return
        self.values["Camera"].setText(theme.camera_name(shot.make, shot.model) if shot.model or shot.make else "—")
        self.values["Serial"].setText(shot.serial or "—")
        self.values["Captured"].setText(
            f"{theme.short_date(shot.taken, year=True)} · {shot.taken:%H:%M}" if shot.taken else "—")
        if shot.shutter_count is None:
            self._show("No count", "THIS FILE HAS NO SHUTTER COUNT",
                       "It may be an edited export, or come from a camera that does not record one. "
                       "Try an original file straight from the camera.")
            self.big.setStyleSheet(f"font-size: 40px; color: {theme.DIM};")
        else:
            self._show(num(shot.shutter_count), "SHUTTER COUNT", "")
            self.big.setStyleSheet("font-size: 64px;")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()
            theme.restyle(self.drop, active=True)

    def dragLeaveEvent(self, _):
        theme.restyle(self.drop, active=False)

    def dropEvent(self, event):
        theme.restyle(self.drop, active=False)
        self.load(event.mimeData().urls()[0].toLocalFile())
