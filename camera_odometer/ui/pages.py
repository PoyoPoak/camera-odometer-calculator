"""Home, Scan and Cameras pages, and the Check Shutter Count and Metadata dialogs."""
from __future__ import annotations

import os
import textwrap
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit,
                               QProgressBar, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..scan import IMAGE_EXTS
from . import theme
from .app import is_enter
from .theme import button, label, num

IMAGE_FILTER = f"Photos ({' '.join('*' + ext for ext in sorted(IMAGE_EXTS))})"


def _column(page: QWidget, width: int) -> QVBoxLayout:
    """A centred column of fixed maximum width inside the page."""
    outer = QHBoxLayout(page)
    outer.setContentsMargins(40, 24, 40, 24)
    holder = QWidget()
    holder.setMaximumWidth(width)
    outer.addStretch(1)
    outer.addWidget(holder, 100)
    outer.addStretch(1)
    col = QVBoxLayout(holder)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(0)
    return col


class _Check(theme.Check):
    """A text-less theme.Check: the whole painted 18 px box takes clicks, not only the style's 14 px
    indicator. ponytail: belongs in theme.Check once another text-less check box appears."""

    def hitButton(self, pos):
        return self.rect().contains(pos)


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
        self.root_list = QWidget()
        self.root_rows = QVBoxLayout(self.root_list)
        self.root_rows.setContentsMargins(0, 0, 0, 0)
        self.root_rows.setSpacing(6)
        self.root_scroll = QScrollArea()  # grows with its rows up to a cap, then scrolls
        self.root_scroll.setWidgetResizable(True)
        self.root_scroll.setWidget(self.root_list)
        self.root_scroll.setFocusPolicy(Qt.NoFocus)
        self.root_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._follow = False  # after an add, keep the end of the list (the new folder) in view
        bar = self.root_scroll.verticalScrollBar()
        bar.rangeChanged.connect(lambda _, end: self._follow and bar.setValue(end))
        col.addWidget(self.root_scroll)
        self.path_row = row = QHBoxLayout()
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
        self.year = QSpinBox()  # arrow keys and the wheel step it
        self.year.setRange(1990, datetime.now().year)
        self.year.setValue(datetime.now().year - 1)
        self.year.setAlignment(Qt.AlignCenter)
        self.year.setFixedWidth(84)
        row.addWidget(self.year)
        row.addStretch(1)
        self.scan_button = button("Scan", "primary", self.scan)
        self.scan_button.setMinimumWidth(140)
        row.addWidget(self.scan_button)
        col.addLayout(row)

        self.error = label("", "error", wrap=True)
        self.error.hide()
        col.addSpacing(16)
        col.addWidget(self.error)
        col.addSpacing(20)

        row = QHBoxLayout()
        row.addWidget(button("Check Shutter Count", on_click=self.check))
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
        # Measured on a row, not the list: rows added to a visible page stay hidden (size 0) until the
        # next event loop pass. Four and a half rows at most, so Home still fits 1100x700 with an error
        # showing; the half row shows that the list scrolls.
        gap = self.root_rows.spacing()
        step = w.sizeHint().height() + gap if self.roots else 0
        self.root_scroll.setFixedHeight(max(round(min(len(self.roots), 4.5) * step) - gap, 0))
        self.path_row.setContentsMargins(0, 6 if self.roots else 0, 0, 0)
        self.path.setPlaceholderText("Paste another folder path and press Enter" if self.roots else
                                     "Paste the path of a folder that holds your photos, or choose Add folder…")

    def add(self, path: str) -> None:
        path = path.strip().strip('"')
        if path:
            path = os.path.normpath(path)
            if os.path.normcase(path) not in map(os.path.normcase, self.roots):
                self.roots.append(path)
                self._follow = True
                self._show_roots()
        self.path.clear()
        self.show_error("")

    def remove(self, root: str) -> None:
        self.roots.remove(root)
        self._follow = False
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
        row.addSpacing(10)
        row.addWidget(label("Esc", "key", align=Qt.AlignCenter))
        row.addStretch(1)
        col.addLayout(row)
        col.addStretch(5)

    def begin(self, roots: list[str], year: int) -> None:
        self.title.setText(f"Scanning for photos taken in {year}")
        names = [os.path.normpath(r) for r in roots]
        if len(names) > 4:  # a long list would push the progress bar off the page
            names = names[:3] + [f"and {len(names) - 3} more"]
        self.root.setText("\n".join(names))
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
        self.cards: list[QWidget] = []
        self.scroll = scroll = QScrollArea()
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
        # Equal stretch on both sides keeps the legend centred in the bar, not between its neighbours.
        row.addLayout(totals, 1)
        row.addWidget(theme.legend(("Enter", "Continue"), ("Esc", "Back")))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(button("Back", "ghost", win.back))
        buttons.addSpacing(8)
        self.next = button("Continue", "primary", self.proceed)
        self.next.setMinimumWidth(140)
        buttons.addWidget(self.next)
        row.addLayout(buttons, 1)
        outer.addWidget(bar)

    def enter(self):
        s = self.win.session
        scan = s.scan
        for card in self.cards:
            card.deleteLater()
        self.cards = [self._card(cam) for cam in scan.cameras]
        if not scan.cameras:
            self.title.setText(f"No photos from {scan.year} were found")
            self.subtitle.setText(
                "The scan looks for original camera files (raw files, or JPEGs straight from the camera) "
                f"taken in {scan.year}. Check that you picked the right folders and tax year, then scan again.")
        else:
            n = len(scan.cameras)
            self.title.setText(f"We found {n} camera{'s' if n != 1 else ''} used in {scan.year}")
            self.subtitle.setText("Each camera's shutter counter works like an odometer: last shot of the year "
                                  "minus first. Untick any camera that should not count, such as a friend's.")
        for text in (self.title, self.subtitle):
            text.setAlignment(Qt.AlignLeft if scan.cameras else Qt.AlignHCenter)
        self.body.setStretch(0, 0 if scan.cameras else 2)
        self.body.setStretch(self.body.count() - 1, 1 if scan.cameras else 3)
        self._place_cards()
        self._refresh_total()
        self.next.setFocus()

    def _place_cards(self) -> None:
        """Up to four cards a row when they fit the window (four bodies is a common kit), else three."""
        while self.grid.count():
            self.grid.takeAt(0)
        n = len(self.cards)
        widest = max((card.minimumSizeHint().width() for card in self.cards), default=1)
        gap = self.grid.spacing()
        cols = 4 if n >= 4 and 4 * widest + 3 * gap <= self.scroll.viewport().width() else min(3, max(1, n))
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // cols, i % cols)
        for c in range(4):
            self.grid.setColumnStretch(c, 1 if c < max(cols, 3) else 0)  # a card is never wider than a third
        for r in range(n + 2):
            self.grid.setRowStretch(r, 1 if r == (n - 1) // cols + 1 else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_cards()

    def _card(self, cam) -> QWidget:
        card = theme.frame("card")
        col = QVBoxLayout(card)
        col.setContentsMargins(22, 20, 22, 20)
        col.setSpacing(0)
        head = QHBoxLayout()
        name = label(theme.camera_name(cam.make, cam.model))
        head.addWidget(name, 1)
        check = _Check()
        check.setFixedSize(20, 20)  # the painted box is 18 px
        check.setToolTip("Include in calculation")
        check.setAccessibleName("Include in calculation")
        check.setCursor(Qt.PointingHandCursor)
        check.setChecked(cam.id not in self.win.session.excluded)
        head.addWidget(check)
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
        if cam.estimated:  # at the foot, not beside the name: there it would stop four cards fitting a row
            col.addSpacing(18)
            badge = label("Estimated from file count", "badge")
            badge.setToolTip("This camera does not record a shutter count, so each file counts as one actuation.")
            col.addWidget(badge, 0, Qt.AlignLeft)

        def shade(on: bool) -> None:  # an excluded camera's card and name are dimmed
            theme.restyle(card, off=not on)
            name.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {theme.TEXT if on else theme.FAINT};")

        shade(check.isChecked())
        check.toggled.connect(lambda on, cid=cam.id: self._toggle(cid, on, shade))
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
        col.addWidget(label("Check Shutter Count", "h2"))
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
        row.setSpacing(8)
        row.addWidget(button("Browse", "primary", self.browse))
        self.path = ""
        self.meta_button = button("View Metadata", on_click=self.view_metadata)
        self.meta_button.setEnabled(False)  # until a photo file is chosen
        row.addWidget(self.meta_button)
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
        self.path = path
        photo = os.path.splitext(path)[1].lower() in IMAGE_EXTS  # ExifTool reads far more than photos
        self.meta_button.setEnabled(photo)
        if not photo:
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

    def view_metadata(self):
        MetadataDialog(self.win, self.path, self).exec()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()
            theme.restyle(self.drop, active=True)

    def dragLeaveEvent(self, _):
        theme.restyle(self.drop, active=False)

    def dropEvent(self, event):
        theme.restyle(self.drop, active=False)
        self.load(event.mimeData().urls()[0].toLocalFile())


class MetadataDialog(QDialog):
    """Every tag ExifTool reads from one photo, in file order, with a filter."""

    def __init__(self, win, path: str, parent=None):
        super().__init__(parent or win)
        self.rows: list[tuple[str, str, str]] = []
        self.setWindowTitle("Metadata")
        self.setModal(True)
        self.resize(760, 560)
        col = QVBoxLayout(self)
        col.setContentsMargins(28, 24, 28, 22)
        col.setSpacing(0)
        name = label(os.path.basename(path), "h2")
        name.setMinimumWidth(40)
        col.addWidget(name)
        col.addSpacing(4)
        self.count = label("", "dim")
        col.addWidget(self.count)
        col.addSpacing(16)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by group, tag or value")
        self.filter.textChanged.connect(self._filter)
        col.addWidget(self.filter)
        col.addSpacing(12)
        self.table = table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Group", "Tag", "Value"])
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 120)
        table.setColumnWidth(1, 230)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(30)
        table.setShowGrid(False)
        table.setWordWrap(False)  # long values are elided; the tooltip has them in full
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        col.addWidget(table, 1)
        self.message = label("", "dim", wrap=True, align=Qt.AlignCenter)
        col.addWidget(self.message, 1)
        col.addSpacing(16)
        row = QHBoxLayout()
        row.addStretch(1)
        close = button("Close", on_click=self.accept)
        close.setAutoDefault(False)  # Enter in the filter must not close the dialog
        row.addWidget(close)
        col.addLayout(row)
        self._message("Reading…")
        win.engine.run(lambda: win.engine.et().metadata(path), self._loaded, self._message)

    def _message(self, text: str) -> None:
        """In place of the table: reading, nothing found, or why the file could not be read."""
        for w in (self.count, self.filter, self.table):
            w.hide()
        self.message.setText(text)
        self.message.show()

    def _loaded(self, rows) -> None:
        if not rows:
            self._message("No metadata was found in this file.")
            return
        self.rows = rows
        self.table.setRowCount(len(rows))
        for r, (group, tag, value) in enumerate(rows):
            # One line per tag, however long: some files hold whole paragraphs or keyword lists.
            for c, text in enumerate((group, tag, " ".join(value[:300].split()))):
                self.table.setItem(r, c, QTableWidgetItem(text))
            self.table.item(r, 0).setForeground(QColor(theme.DIM))
            self.table.item(r, 2).setToolTip(textwrap.fill(value[:2000], 100) + "…" * (len(value) > 2000))
        self.message.hide()
        for w in (self.count, self.filter, self.table):
            w.show()
        self._filter(self.filter.text())
        self.filter.setFocus()

    def _filter(self, text: str) -> None:
        text = text.casefold()
        shown = 0
        for r, row in enumerate(self.rows):
            hit = text in " ".join(row).casefold()
            self.table.setRowHidden(r, not hit)
            shown += hit
        total = len(self.rows)
        self.count.setText(f"{num(total)} tags" if shown == total else f"{num(shown)} of {num(total)} tags")
