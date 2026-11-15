"""Classify page: folder tree, folder card, and the Personal / Business targets."""
from __future__ import annotations

import os

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QSizePolicy, QStyle, QStyledItemDelegate,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..calc import effective_label
from ..models import BUSINESS, PERSONAL
from . import theme
from .app import classified, is_enter
from .theme import LABEL_COLOR, LABEL_TEXT, button, label, num

REL = Qt.UserRole
INDENT = 18
ROW_H = 34
FLASH_MS = 150
SLIDE_PX = 22


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
    """Up to 8 evenly spaced thumbnails: two rows of four when there is room, else one row."""

    def __init__(self):
        super().__init__()
        self.images, self.message = [], ""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(64)

    def show_images(self, images, message: str = "") -> None:
        self.images, self.message = list(images), message
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        n, gap = len(self.images), 8
        if not n:
            p.setPen(QColor(theme.FAINT))
            p.drawText(self.rect(), Qt.AlignCenter, self.message)
            return
        rows, cols = (2, (n + 1) // 2) if n > 4 else (1, n)
        cols = max(cols, 4)
        w = (self.width() - gap * (cols - 1)) / cols
        if rows == 2 and 2 * (w * 2 / 3) + gap > self.height():
            rows, cols = 1, n
            w = (self.width() - gap * (cols - 1)) / cols
        h = min(w * 2 / 3, (self.height() - gap * (rows - 1)) / rows)
        for i, img in enumerate(self.images):
            cell = QRectF((i % cols) * (w + gap), (i // cols) * (h + gap), w, h)
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
        self._picks: dict[str, tuple[list[str], int]] = {}  # rel -> (strip paths, image count)
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

        self.banner = theme.frame("banner")
        row = QHBoxLayout(self.banner)
        row.setContentsMargins(16, 10, 10, 10)
        self.banner_text = label("")
        row.addWidget(self.banner_text, 1)
        row.addWidget(label("Ctrl+Enter", "faint"))
        row.addSpacing(6)
        row.addWidget(button("See results", "primary", lambda: win.go("results"), focus=False))
        wrap = QVBoxLayout()
        wrap.setContentsMargins(24, 20, 24, 0)
        wrap.addWidget(self.banner)
        right.addLayout(wrap)

        self.card_host = QVBoxLayout()
        self.card_host.setContentsMargins(24, 20, 24, 20)
        right.addLayout(self.card_host, 1)
        self.card = theme.frame("card")
        self.card_host.addWidget(self.card)
        col = QVBoxLayout(self.card)
        col.setContentsMargins(28, 24, 28, 22)
        col.setSpacing(0)
        self.crumb = label("", "faint")
        self.title = label("", "h1")
        self.title.setMinimumWidth(40)
        self.dates = label("", "dim")
        self.state = label("")
        col.addWidget(self.crumb)
        col.addWidget(self.title)
        col.addSpacing(4)
        row = QHBoxLayout()
        row.addWidget(self.dates)
        row.addStretch(1)
        row.addWidget(self.state)
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
        self.strip_note = label("", "faint")
        col.addWidget(self.strip_note)

        bar = theme.frame("bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 14, 24, 14)
        row.addWidget(button("←   PERSONAL", "personal", lambda: self.mark(PERSONAL), focus=False))
        hints = label("↑ ↓  move    ·    Enter  gallery    ·    Space  expand    ·    Backspace  clear"
                      "    ·    Ctrl+Enter  results", "faint", align=Qt.AlignCenter)
        hints.setMinimumWidth(40)
        row.addWidget(hints, 1)
        row.addWidget(button("BUSINESS   →", "business", lambda: self.mark(BUSINESS), focus=False))
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
        self._picks.clear()
        self.folders = {f.rel: f for f in scan.folders}
        self.tree.clear()
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
        self.win.set_status(f"{num(done)} / {num(total)} classified")
        self.banner.setVisible(bool(total) and done == total)
        self.banner_text.setText(f"All {num(total)} folders are classified.")
        self.tree.viewport().update()
        self._show_state()

    def _show_state(self) -> None:
        rel = self.current
        if rel is None:
            return
        own, eff = self.labels.get(rel), effective_label(rel, self.labels)
        if eff is None:
            self.state.setText("Not classified")
            self.state.setStyleSheet(f"color: {theme.FAINT};")
        else:
            text = LABEL_TEXT[eff]
            if not own:
                text += " · inherited"
            self.state.setText(text)
            self.state.setStyleSheet(f"color: {LABEL_COLOR[eff]}; font-weight: 600;")

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
            for i, r in enumerate(folder.ranges):
                cam = cams.get(r.camera_id)
                name = label(theme.camera_name(cam.make, cam.model) if cam else r.first.model)
                name.setStyleSheet("font-weight: 600;")
                if r.estimated:
                    span, count = "estimated from file count", f"{num(r.frames)} files"
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
        if rel not in self._picks or any(not self.win.engine.has_thumb(p) for p in self._picks[rel][0]):
            self._strip_timer.start()

    # -- thumbnails --

    def _show_strip(self, error: str | None = None) -> None:
        rel = self.current
        paths, total = self._picks.get(rel, ([], None))
        if total is None:
            self.strip.show_images([], "Loading previews…")
            self.strip_note.setText("")
            return
        images = [self.win.engine.thumb(p) for p in paths]
        if not total:
            self.strip.show_images([], "No photos directly in this folder.")
        elif error or (all(i is None for i in images) and all(self.win.engine.has_thumb(p) for p in paths)):
            self.strip.show_images([], error or "No previews are available for these files.")
        else:
            self.strip.show_images(images)
        self.strip_note.setText(f"Enter opens all {num(total)} photos in this folder" if total else "")

    def _load_strip(self) -> None:
        rel = self.current
        if rel is None:
            return
        path = self.folders[rel].path if rel in self.folders else os.path.join(self._scan.root, rel)
        engine = self.win.engine

        def pick():
            images = self.win.list_images(path)
            n = min(8, len(images))
            return [images[i * (len(images) - 1) // max(n - 1, 1)] for i in range(n)], len(images)

        def got(result):
            self._picks[rel] = result
            engine.load_thumbs(result[0], lambda error=None: rel == self.current and self._show_strip(error))

        def failed(message):
            self._picks[rel] = ([], 0)
            if rel == self.current:
                self.strip.show_images([], message)

        if rel in self._picks:
            got(self._picks[rel])
        else:
            engine.run(pick, got, failed)

    # -- actions --

    def mark(self, value: str) -> None:
        self._finish_flash()
        rel = self.current
        if rel is None:
            return
        self.labels[rel] = value
        self._refresh()
        self.win.save()  # after the refresh, so a failed save stays visible in the status
        self._flash_rel = rel
        self._direction = -1 if value == PERSONAL else 1
        theme.restyle(self.card, flash=value)
        self.anim.start()

    def _slide(self, t: float) -> None:
        d = round(SLIDE_PX * t) * getattr(self, "_direction", 0)
        self.card_host.setContentsMargins(24 + d, 20, 24 - d, 20)

    def _flash_done(self) -> None:
        """The flash is over: put the card back and move on to the next unclassified folder."""
        rel, self._flash_rel = self._flash_rel, None
        if rel is None:
            return
        self.card_host.setContentsMargins(24, 20, 24, 20)
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
            self.win.save()

    def move(self, step: int) -> None:
        item = self.tree.currentItem()
        target = (self.tree.itemBelow(item) if step > 0 else self.tree.itemAbove(item)) if item else None
        if target:
            self.tree.setCurrentItem(target)

    def toggle(self) -> None:
        item = self.tree.currentItem()
        if item and item.childCount():
            item.setExpanded(not item.isExpanded())

    def open_gallery(self) -> None:
        rel = self.current
        if rel is not None:
            path = self.folders[rel].path if rel in self.folders else os.path.join(self._scan.root, rel)
            self.win.pages["gallery"].open(rel, self.items[rel].text(0), path)

    def handle_key(self, event) -> bool:
        if is_enter(event, ctrl=True):
            self._finish_flash()
            self.win.go("results")
            return True
        if event.modifiers() & ~Qt.KeypadModifier:
            return False
        key = event.key()
        action = {Qt.Key_Left: lambda: self.mark(PERSONAL), Qt.Key_Right: lambda: self.mark(BUSINESS),
                  Qt.Key_Up: lambda: self.move(-1), Qt.Key_Down: lambda: self.move(1),
                  Qt.Key_Backspace: self.clear, Qt.Key_Space: self.toggle,
                  Qt.Key_Return: self.open_gallery, Qt.Key_Enter: self.open_gallery}.get(key)
        if action is None:
            return False
        self._finish_flash()
        action()
        return True
