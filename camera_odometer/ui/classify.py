"""Classify page: folder tree, the selected folder's details and previews, and the label buttons."""
from __future__ import annotations

import math
import os

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QSizePolicy, QStyle, QStyledItemDelegate,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..calc import effective_label
from ..models import BUSINESS, PERSONAL
from . import theme
from .app import classified
from .theme import LABEL_COLOR, LABEL_TEXT, button, label, num

REL = Qt.UserRole
INDENT = 18
ROW_H = 34
FLASH_MS = 150
SLIDE_PX = 22
PANE_MARGINS = (12, 12, 12, 8)  # around the selected folder's pane; the flash slides it sideways
THUMB_W = (120, 240)  # narrowest and widest a preview may get
GAP = 8


def _depth(item: QTreeWidgetItem) -> int:
    d = 0
    while item.parent():
        item, d = item.parent(), d + 1
    return d


class Tree(QTreeWidget):
    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item and item.childCount() and event.position().x() < 12 + _depth(item) * INDENT + 18:
            item.setExpanded(not item.isExpanded())  # a click on the chevron
            return
        super().mousePressEvent(event)


class RowDelegate(QStyledItemDelegate):
    """Chevron, status dot, folder name and label chip. Colour is never the only signal."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page

    def sizeHint(self, option, index):
        return QSize(0, ROW_H)

    def paint(self, p: QPainter, option, index):
        page = self.page
        item = page.tree.itemFromIndex(index)
        rel = index.data(REL)
        own = page.labels.get(rel)
        eff = effective_label(rel, page.labels)
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            p.setPen(QPen(QColor("#3d3d44"), 1))
            p.setBrush(QColor(theme.RAISED))
            p.drawRoundedRect(r.adjusted(6.5, 1.5, -6.5, -1.5), 6, 6)
        elif option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.SURFACE))
            p.drawRoundedRect(r.adjusted(6, 1, -6, -1), 6, 6)

        x = r.left() + 14 + _depth(item) * INDENT
        cy = r.center().y()
        if item.childCount():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.DIM))
            if item.isExpanded():
                tri = [QPointF(x, cy - 2.5), QPointF(x + 9, cy - 2.5), QPointF(x + 4.5, cy + 3.5)]
            else:
                tri = [QPointF(x + 2, cy - 4.5), QPointF(x + 8, cy), QPointF(x + 2, cy + 4.5)]
            p.drawPolygon(QPolygonF(tri))
        x += 18

        color = QColor(LABEL_COLOR[eff])
        if eff and not own:
            color.setAlphaF(0.45)  # inherited: dimmed
        if eff:
            p.setPen(Qt.NoPen)
            p.setBrush(color)
        else:
            p.setPen(QPen(QColor(theme.FAINT if rel not in page.folders else theme.UNCLASSIFIED), 1.4))
            p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(x + 5, cy), 4.5, 4.5)
        x += 20

        right = r.right() - 16
        if eff:
            f = QFont(option.font)
            f.setPixelSize(10)
            f.setBold(True)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
            p.setFont(f)
            text = LABEL_TEXT[eff].upper()
            w = p.fontMetrics().horizontalAdvance(text) + 14
            chip = QRectF(right - w, cy - 9, w, 18)
            fill = QColor(LABEL_COLOR[eff])
            fill.setAlphaF(0.07 if not own else 0.16)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(chip, 9, 9)
            p.setPen(color)
            p.drawText(chip, Qt.AlignCenter, text)
            right = chip.left() - 8
            if not own:
                f = QFont(option.font)
                f.setPixelSize(12)
                p.setFont(f)
                p.setPen(QColor(theme.FAINT))
                w = p.fontMetrics().horizontalAdvance("(inherit)")
                p.drawText(QRectF(right - w, r.top(), w, r.height()), Qt.AlignVCenter, "(inherit)")
                right -= w + 8

        p.setFont(option.font)
        p.setPen(QColor(theme.TEXT if rel in page.folders else theme.DIM))
        name = p.fontMetrics().elidedText(index.data(Qt.DisplayRole), Qt.ElideRight, int(right - x))
        p.drawText(QRectF(x, r.top(), right - x, r.height()), Qt.AlignVCenter | Qt.AlignLeft, name)
        p.restore()


class ThumbStrip(QWidget):
    """Evenly spaced previews that fill the space: as many 3:2 cells as fit, row after row."""

    resized = Signal()

    def __init__(self):
        super().__init__()
        self.images, self.message = [], ""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(64)

    def _grid(self, n: int) -> tuple[int, int, float, float]:
        """(columns, rows, cell width, cell height) that cover the most of the strip with n photos:
        a short strip gets more, smaller previews instead of one row and empty space below."""
        best, best_area = None, -1.0
        fewest = max(1, math.ceil((self.width() + GAP) / (THUMB_W[1] + GAP)))
        for cols in range(fewest, max(fewest, int((self.width() + GAP) // (THUMB_W[0] + GAP))) + 1):
            w = (self.width() - GAP * (cols - 1)) / cols
            h = min(w * 2 / 3, self.height())
            w = h * 3 / 2  # a strip shorter than one row narrows the cells, never crops them wider
            rows = max(1, int((self.height() + GAP) // (h + GAP)))
            area = min(cols * rows, n) * w * h
            if area > best_area:
                best, best_area = (cols, rows, w, h), area
        return best

    def capacity(self, n: int) -> int:
        """How many of a folder's n photos the strip shows."""
        cols, rows, _, _ = self._grid(n)
        return min(cols * rows, n)

    def show_images(self, images, message: str = "") -> None:
        self.images, self.message = list(images), message
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        if not self.images:
            p.setPen(QColor(theme.FAINT))
            p.drawText(self.rect(), Qt.AlignCenter, self.message)
            return
        cols, rows, w, h = self._grid(len(self.images))
        for i, img in enumerate(self.images[:cols * rows]):
            cell = QRectF((i % cols) * (w + GAP), (i // cols) * (h + GAP), w, h)
            path = QPainterPath()
            path.addRoundedRect(cell, 5, 5)
            p.setClipPath(path)
            p.fillRect(cell, QColor(theme.RAISED))
            if img is not None:
                p.drawImage(cell, img, _cover(img, cell))


def _cover(img, cell: QRectF) -> QRectF:
    """The centred part of img with the cell's aspect ratio (crop to fill)."""
    iw, ih, ratio = img.width(), img.height(), cell.width() / max(cell.height(), 1)
    if iw / ih > ratio:
        w = ih * ratio
        return QRectF((iw - w) / 2, 0, w, ih)
    h = iw / ratio
    return QRectF(0, (ih - h) / 2, iw, h)


class ClassifyPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._scan = None
        self.labels: dict[str, str] = {}
        self.folders: dict[str, object] = {}  # rel -> Folder, only folders that hold in-year shots
        self.items: dict[str, QTreeWidgetItem] = {}
        self.order: list[str] = []  # every row in tree order, collapsed or not
        self._photos: dict[str, list[str]] = {}  # rel -> the folder's photos, listed once
        self._flash_rel: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        split = QHBoxLayout()
        split.setSpacing(0)
        outer.addLayout(split, 1)

        self.tree = Tree()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setMouseTracking(True)
        self.tree.setVerticalScrollMode(QTreeWidget.ScrollPerPixel)
        self.tree.setItemDelegate(RowDelegate(self))
        self.tree.setMinimumWidth(380)
        self.tree.setMaximumWidth(460)
        self.tree.currentItemChanged.connect(lambda *_: self._selection_changed())
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_gallery())
        left = QVBoxLayout()
        left.setContentsMargins(8, 14, 0, 8)
        left.addWidget(self.tree)
        split.addLayout(left, 4)
        vline = theme.frame("line")
        vline.setStyleSheet("min-height: 0; max-height: 16777215px; min-width: 1px; max-width: 1px;")
        split.addWidget(vline)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        split.addLayout(right, 7)

        # The selected folder fills the right side. No card: it is the one thing there. The pane
        # only shows itself while it flashes a label colour.
        self.card_host = QVBoxLayout()
        self.card_host.setContentsMargins(*PANE_MARGINS)
        right.addLayout(self.card_host, 1)
        self.card = theme.frame("pane")
        self.card_host.addWidget(self.card)
        col = QVBoxLayout(self.card)
        col.setContentsMargins(24, 18, 24, 14)
        col.setSpacing(0)
        self.crumb = label("", "faint")
        self.title = label("", "h1")
        self.title.setMinimumWidth(40)
        self.dates = label("", "dim")
        col.addWidget(self.crumb)
        col.addWidget(self.title)
        col.addSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.dates)
        row.addStretch(1)
        self.inherited = label("Inherited", "faint")
        row.addWidget(self.inherited)
        self.toggles = {}
        for value in (PERSONAL, BUSINESS):
            b = button(LABEL_TEXT[value], value, lambda value=value: self.mark(value), focus=False)
            b.setToolTip(f"Mark this folder {LABEL_TEXT[value]} ({'←' if value == PERSONAL else '→'})")
            self.toggles[value] = b
            row.addWidget(b)
        col.addLayout(row)
        col.addSpacing(18)
        col.addWidget(theme.frame("line"))
        col.addSpacing(16)
        self.bodies = QGridLayout()
        self.bodies.setHorizontalSpacing(20)
        self.bodies.setVerticalSpacing(2)
        self.bodies.setColumnStretch(0, 1)
        col.addLayout(self.bodies)
        col.addSpacing(20)
        self.strip = ThumbStrip()
        col.addWidget(self.strip, 1)
        col.addSpacing(12)
        self.strip.resized.connect(self._strip_resized)
        self.strip_note = label("", "faint")
        col.addWidget(self.strip_note)

        bar = theme.frame("bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(40, 16, 24, 16)
        count = QVBoxLayout()
        count.setSpacing(0)
        self.done = label("", "num")
        count.addWidget(self.done)
        count.addWidget(label("FOLDERS CLASSIFIED", "caps"))
        row.addLayout(count)
        row.addStretch(1)
        row.addWidget(theme.legend(("←", "Personal"), ("→", "Business"), (("↑", "↓"), "Move"),
                                   ("Space", "Gallery"), ("Backspace", "Clear"), ("Enter", "Results")))
        row.addStretch(1)
        results = button("See Results", "primary", lambda: self.see_results(), focus=False)
        results.setMinimumWidth(140)
        row.addWidget(results)
        outer.addWidget(bar)

        self.anim = QVariantAnimation(self)
        self.anim.setDuration(FLASH_MS)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._slide)
        self.anim.finished.connect(self._flash_done)
        self._strip_timer = QTimer(self)
        self._strip_timer.setSingleShot(True)
        self._strip_timer.setInterval(120)  # holding an arrow key must not queue a read per folder
        self._strip_timer.timeout.connect(self._load_strip)

    # -- building --

    def enter(self):
        session = self.win.session
        self.labels = session.labels
        if session.scan is not self._scan:
            self._build(session.scan)
        self._refresh()
        if self.tree.currentItem() is None:
            self._select(self._next_unclassified(None) or next(iter(self.folders), self.order[0]))
        self.tree.setFocus()

    def _build(self, scan) -> None:
        self._scan = scan
        self._photos.clear()
        self.folders = {f.rel: f for f in scan.folders}
        self.tree.clear()
        root_name = "Photo folders"  # folders on different drives have no common parent
        if scan.root:
            root_name = os.path.basename(os.path.normpath(scan.root)) or scan.root
        self.items = {"": QTreeWidgetItem(self.tree, [root_name])}
        self.items[""].setData(0, REL, "")
        for rel in sorted(self.folders):
            parts = rel.split("/") if rel else []
            for i in range(1, len(parts) + 1):
                sub = "/".join(parts[:i])
                if sub not in self.items:
                    item = QTreeWidgetItem(self.items["/".join(parts[:i - 1])], [parts[i - 1]])
                    item.setData(0, REL, sub)
                    self.items[sub] = item
        self.tree.expandAll()
        self.order = []

        def walk(item):
            self.order.append(item.data(0, REL))
            for i in range(item.childCount()):
                walk(item.child(i))

        walk(self.items[""])

    # -- state --

    @property
    def current(self) -> str | None:
        item = self.tree.currentItem()
        return item.data(0, REL) if item else None

    def _select(self, rel: str) -> None:
        item = self.items[rel]
        parent = item.parent()
        while parent:
            parent.setExpanded(True)
            parent = parent.parent()
        self.tree.setCurrentItem(item)
        self.tree.scrollToItem(item)

    def _next_unclassified(self, after: str | None) -> str | None:
        """Next folder holding shots with no effective label, in tree order, wrapping once."""
        start = self.order.index(after) + 1 if after in self.order else 0
        for rel in self.order[start:] + self.order[:start]:
            if rel in self.folders and effective_label(rel, self.labels) is None:
                return rel
        return None

    def _refresh(self) -> None:
        """Everything that depends on the labels."""
        done, total = classified(self.win.session)
        self.done.setText(f"{num(done)} / {num(total)}")
        self.tree.viewport().update()
        self._show_state()

    def _show_state(self) -> None:
        """The label buttons: lit for the folder's own label, tinted for an inherited one."""
        rel = self.current
        if rel is None:
            return
        own, eff = self.labels.get(rel), effective_label(rel, self.labels)
        for value, b in self.toggles.items():
            theme.restyle(b, on="own" if own == value else "inherited" if not own and eff == value else "")
        self.inherited.setVisible(bool(eff) and not own)

    def _selection_changed(self) -> None:
        rel = self.current
        if rel is None:
            return
        folder = self.folders.get(rel)
        parent = rel.rpartition("/")[0]
        self.crumb.setText(parent.replace("/", "  ›  "))
        self.crumb.setVisible(bool(parent))
        self.title.setText(self.items[rel].text(0))
        while self.bodies.count():
            self.bodies.takeAt(0).widget().deleteLater()
        if folder:
            taken = [s.taken for r in folder.ranges for s in (r.first, r.last) if s.taken]
            self.dates.setText(theme.date_range(min(taken), max(taken)) if taken else "No capture dates")
            cams = {c.id: c for c in self._scan.cameras}
            runs: dict[str, list] = {}  # a sparse folder holds several runs (days) of one body
            for r in folder.ranges:
                runs.setdefault(r.camera_id, []).append(r)
            for i, (cid, rs) in enumerate(runs.items()):
                r, cam = rs[0], cams.get(cid)
                name = label(theme.camera_name(cam.make, cam.model) if cam else r.first.model)
                name.setStyleSheet("font-weight: 600;")
                if r.estimated:
                    span, count = "estimated from file count", f"{num(r.frames)} files"
                elif len(rs) > 1:
                    span, count = f"{len(rs)} separate days", f"{num(sum(x.actuations for x in rs))} shots"
                else:
                    span = f"#{num(r.first.shutter_count)}  →  #{num(r.last.shutter_count)}"
                    count = f"{num(r.actuations)} shots"
                if cam and cam.id in self.win.session.excluded:
                    span += "  ·  not included"
                big = label(count, align=Qt.AlignRight | Qt.AlignVCenter)
                big.setStyleSheet("font-size: 20px; font-weight: 300;")
                self.bodies.addWidget(name, i * 2, 0)
                self.bodies.addWidget(label(span, "dim", align=Qt.AlignRight | Qt.AlignVCenter), i * 2, 1)
                self.bodies.addWidget(big, i * 2, 2)
                spacer = QWidget()
                spacer.setFixedHeight(6)
                self.bodies.addWidget(spacer, i * 2 + 1, 0)
        else:
            inside = [f for r, f in self.folders.items() if not rel or r.startswith(rel + "/")]
            shots = sum(r.actuations for f in inside for r in f.ranges)
            self.dates.setText(f"{len(inside)} folder{'s' if len(inside) != 1 else ''} inside · {num(shots)} shots")
            self.bodies.addWidget(label("No photos from this year sit directly in this folder. A label here "
                                        "applies to every folder inside it that has no label of its own.",
                                        "dim", wrap=True), 0, 0)
        self._show_state()
        self._show_strip()
        self._strip_resized()

    # -- thumbnails --

    def _picks(self, rel: str) -> list[str]:
        """As many of the folder's photos as the strip has room for, evenly spaced through it."""
        photos = self._photos.get(rel, [])
        n = self.strip.capacity(len(photos))
        return [photos[i * (len(photos) - 1) // max(n - 1, 1)] for i in range(n)]

    def _strip_resized(self) -> None:
        """A new folder or a new strip size: read the previews still missing, once the keys or the
        resizing pause."""
        rel = self.current
        if rel is not None and (rel not in self._photos
                                or any(not self.win.engine.has_thumb(p) for p in self._picks(rel))):
            self._strip_timer.start()
        else:
            self._show_strip()

    def _show_strip(self, error: str | None = None) -> None:
        rel = self.current
        if rel not in self._photos:
            self.strip.show_images([], "Loading previews…")
            self.strip_note.setText("")
            return
        total, paths = len(self._photos[rel]), self._picks(rel)
        images = [self.win.engine.thumb(p) for p in paths]
        if not total:
            self.strip.show_images([], "No photos directly in this folder.")
        elif error or (all(i is None for i in images) and all(self.win.engine.has_thumb(p) for p in paths)):
            self.strip.show_images([], error or "No previews are available for these files.")
        else:
            self.strip.show_images(images)
        self.strip_note.setText(f"Space opens all {num(total)} photos in this folder" if total else "")

    def _load_strip(self) -> None:
        rel = self.current
        if rel is None:
            return
        engine = self.win.engine

        def listed(photos):
            self._photos[rel] = photos
            engine.load_thumbs(self._picks(rel), lambda error=None: rel == self.current and self._show_strip(error))

        def failed(message):
            self._photos[rel] = []
            if rel == self.current:
                self.strip.show_images([], message)

        if rel in self._photos:
            listed(self._photos[rel])
        else:  # rows that only group other folders have no photos of their own to show
            engine.run(lambda: self.win.list_images(self.folders[rel].path) if rel in self.folders else [],
                       listed, failed)

    # -- actions --

    def mark(self, value: str) -> None:
        self._finish_flash()
        rel = self.current
        if rel is None:
            return
        self.labels[rel] = value
        self._refresh()
        self.win.unsaved = True
        self._flash_rel = rel
        self._direction = -1 if value == PERSONAL else 1
        theme.restyle(self.card, flash=value)
        self.anim.start()

    def _slide(self, t: float) -> None:
        d = round(SLIDE_PX * t) * getattr(self, "_direction", 0)
        left, top, right, bottom = PANE_MARGINS
        self.card_host.setContentsMargins(left + d, top, right - d, bottom)

    def _flash_done(self) -> None:
        """The flash is over: put the card back and move on to the next unclassified folder."""
        rel, self._flash_rel = self._flash_rel, None
        if rel is None:
            return
        self.card_host.setContentsMargins(*PANE_MARGINS)
        theme.restyle(self.card, flash="")
        target = self._next_unclassified(rel)
        if target:
            self._select(target)

    def _finish_flash(self) -> None:
        """A key pressed during the flash applies to the folder the flash was heading to."""
        if self._flash_rel is not None:
            self.anim.stop()
            self._flash_done()

    def clear(self) -> None:
        changed = self.current is not None and self.labels.pop(self.current, None)
        self._refresh()
        if changed:
            self.win.unsaved = True

    def move(self, step: int) -> None:
        item = self.tree.currentItem()
        target = (self.tree.itemBelow(item) if step > 0 else self.tree.itemAbove(item)) if item else None
        if target:
            self.tree.setCurrentItem(target)

    def open_gallery(self) -> None:
        rel = self.current
        if rel is not None:
            path = self.folders[rel].path if rel in self.folders else ""
            self.win.pages["gallery"].open(rel, self.items[rel].text(0), path)

    def open_folder(self, rel: str) -> None:
        """From Results: Classify on that folder, with its photos open. Esc then lands on the folder."""
        self.win.go("classify")
        if rel in self.items:
            self._select(rel)
            self.open_gallery()

    def see_results(self) -> None:
        self._finish_flash()
        self.win.go("results")

    def handle_key(self, event) -> bool:
        if event.modifiers() & ~Qt.KeypadModifier:
            return False
        key = event.key()
        action = {Qt.Key_Left: lambda: self.mark(PERSONAL), Qt.Key_Right: lambda: self.mark(BUSINESS),
                  Qt.Key_Up: lambda: self.move(-1), Qt.Key_Down: lambda: self.move(1),
                  Qt.Key_Backspace: self.clear, Qt.Key_Space: self.open_gallery,
                  Qt.Key_Return: self.see_results, Qt.Key_Enter: self.see_results}.get(key)
        if action is None:
            return False
        self._finish_flash()
        action()
        return True
