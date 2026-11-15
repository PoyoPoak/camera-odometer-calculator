"""Gallery: lazy thumbnail grid of one folder, and the single-image view."""
from __future__ import annotations

import os
from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QListView, QStackedWidget, QStyle, QStyledItemDelegate,
                               QVBoxLayout, QWidget)

from ..calc import effective_label
from ..models import BUSINESS, PERSONAL
from . import theme
from .app import is_enter
from .theme import LABEL_COLOR, LABEL_TEXT, button, label, num

CELL_W = 196
CAPTION_H = 26


def _fit(img, box: QRectF) -> QRectF:
    """Largest rect with the image's aspect ratio centred in box."""
    size = QSize(img.width(), img.height()).scaled(box.size().toSize(), Qt.KeepAspectRatio)
    return QRectF(box.center().x() - size.width() / 2, box.center().y() - size.height() / 2,
                  size.width(), size.height())


class PathModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.paths: list[str] = []

    def reset(self, paths: list[str]) -> None:
        self.beginResetModel()
        self.paths = paths
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.paths)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return os.path.basename(self.paths[index.row()])
        return None


class CellDelegate(QStyledItemDelegate):
    def __init__(self, page):
        super().__init__(page)
        self.page = page

    def sizeHint(self, option, index):
        return self.page.grid.gridSize()

    def paint(self, p: QPainter, option, index):
        engine = self.page.win.engine
        path = self.page.model.paths[index.row()]
        cell = QRectF(option.rect).adjusted(6, 6, -6, -6)
        box = cell.adjusted(0, 0, 0, -CAPTION_H)
        selected = bool(option.state & QStyle.State_Selected)
        p.save()
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.RAISED if selected else theme.SURFACE))
        p.drawRoundedRect(box, 5, 5)
        img = engine.thumb(path)
        if img is not None:
            p.drawImage(_fit(img, box.adjusted(4, 4, -4, -4)), img)
        elif engine.has_thumb(path):
            p.setPen(QColor(theme.FAINT))
            p.drawText(box, Qt.AlignCenter, "No preview")
        if selected:
            p.setPen(QPen(QColor(theme.TEXT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box.adjusted(1, 1, -1, -1), 5, 5)
        f = p.font()
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT if selected else theme.FAINT))
        caption = QRectF(cell.left(), box.bottom(), cell.width(), CAPTION_H)
        p.drawText(caption, Qt.AlignCenter,
                   p.fontMetrics().elidedText(index.data(), Qt.ElideMiddle, int(cell.width())))
        p.restore()


class Viewer(QWidget):
    """One image, as large as the window allows."""

    def __init__(self):
        super().__init__()
        self.image, self.sharp, self.caption = None, False, ""

    def show_image(self, image, sharp: bool, caption: str) -> None:
        self.image, self.sharp, self.caption = image, sharp, caption
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#0b0b0c"))
        area = QRectF(self.rect()).adjusted(24, 20, -24, -52)
        if self.image is not None:
            p.drawImage(_fit(self.image, area), self.image)
        text = self.caption
        if self.image is None:
            p.setPen(QColor(theme.FAINT))
            p.drawText(area, Qt.AlignCenter, "No preview in this file" if self.sharp else "Loading…")
        elif not self.sharp:
            text += "   ·   loading full preview…"
        p.setPen(QColor(theme.DIM))
        p.drawText(QRectF(0, self.height() - 44, self.width(), 32), Qt.AlignCenter, text)


class GalleryPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.rel, self._path = "", ""
        self._pending: set[str] = set()
        self._previews: OrderedDict[str, object] = OrderedDict()  # the last few large previews
        self._token = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(16, 12, 24, 12)
        head.setSpacing(12)
        head.addWidget(button("←  Back", "ghost", self.step_back, focus=False))
        self.title = label("")
        self.title.setStyleSheet("font-size: 17px; font-weight: 600;")
        self.count = label("", "dim")
        self.state = label("")
        head.addWidget(self.title)
        head.addWidget(self.count)
        head.addWidget(self.state)
        head.addStretch(1)
        self.hints = label("", "faint")
        head.addWidget(self.hints)
        outer.addLayout(head)
        outer.addWidget(theme.frame("line"))

        self.model = PathModel()
        self.grid = QListView()
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setSelectionMode(QListView.SingleSelection)
        self.grid.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)  # keeps the column maths stable
        self.grid.setGridSize(QSize(CELL_W, CELL_W * 2 // 3 + CAPTION_H))
        self.grid.setModel(self.model)
        self.grid.setItemDelegate(CellDelegate(self))
        self.grid.doubleClicked.connect(lambda _: self.open_image())
        self.grid.verticalScrollBar().valueChanged.connect(lambda _: self._lazy.start())
        self.grid.installEventFilter(self)
        self.empty = label("", "dim", align=Qt.AlignCenter, wrap=True)
        self.viewer = Viewer()
        self.stack = QStackedWidget()
        grid_wrap = QWidget()
        wrap = QVBoxLayout(grid_wrap)
        wrap.setContentsMargins(18, 12, 8, 0)
        wrap.addWidget(self.grid)
        for w in (grid_wrap, self.empty, self.viewer):
            self.stack.addWidget(w)
        outer.addWidget(self.stack, 1)

        self._lazy = QTimer(self)
        self._lazy.setSingleShot(True)
        self._lazy.setInterval(60)  # one batch per pause in scrolling, not one per pixel
        self._lazy.timeout.connect(self._load_visible)

    # -- opening --

    def open(self, rel: str, name: str, path: str) -> None:
        self.rel, self._path = rel, path
        self._token += 1
        token = self._token
        self.title.setText(name)
        self.count.setText("")
        self.model.reset([])
        self.empty.setText("Loading…")
        self.stack.setCurrentWidget(self.empty)
        self.win.go("gallery")
        self.win.engine.run(lambda: self.win.list_images(path),
                            lambda paths: token == self._token and self._listed(paths),
                            lambda message: token == self._token and self.empty.setText(message))

    def _listed(self, paths: list[str]) -> None:
        self.count.setText(f"{num(len(paths))} photo{'s' if len(paths) != 1 else ''}")
        if not paths:
            self.empty.setText("There are no photos directly in this folder.\nPress Esc to go back.")
            return
        self.model.reset(paths)
        self.stack.setCurrentIndex(0)
        self._fit_columns()
        self.grid.setCurrentIndex(self.model.index(0))
        self.grid.setFocus()
        self._lazy.start()

    def enter(self):
        eff = effective_label(self.rel, self.win.session.labels)
        self.state.setText(LABEL_TEXT[eff])
        self.state.setStyleSheet(f"color: {LABEL_COLOR[eff]}; font-weight: 600;")
        self._hints()
        self.win.pages["classify"]._refresh()  # keeps the "N / M classified" status visible here too

    def _hints(self) -> None:
        if self.stack.currentWidget() is self.viewer:
            self.hints.setText("←  →  flip    ·    P  personal    ·    B  business    ·    Esc  grid")
        else:
            self.hints.setText("Arrows  move    ·    Enter  open    ·    P  personal    ·    B  business"
                               "    ·    Esc  back")

    # -- lazy thumbnails --

    def _fit_columns(self) -> None:
        width = self.grid.viewport().width()
        cols = max(1, width // CELL_W)
        cell = width // cols
        self.grid.setGridSize(QSize(cell, (cell - 12) * 2 // 3 + 12 + CAPTION_H))

    def eventFilter(self, obj, event):
        if obj is self.grid and event.type() == event.Type.Resize:
            QTimer.singleShot(0, self._fit_columns)
            self._lazy.start()
        return False

    def _visible_rows(self) -> range:
        size = self.grid.gridSize()
        cols = max(1, self.grid.viewport().width() // max(size.width(), 1))
        index = self.grid.indexAt(QPoint(size.width() // 2, size.height() // 2))
        if not index.isValid():
            index = self.grid.indexAt(QPoint(size.width() // 2, 4))
        first = index.row() if index.isValid() else 0
        rows = self.grid.viewport().height() // max(size.height(), 1) + 2
        return range(max(0, first - cols), min(len(self.model.paths), first + rows * cols))

    def _load_visible(self) -> None:
        engine = self.win.engine
        want = [self.model.paths[i] for i in self._visible_rows()]
        want = [p for p in want if not engine.has_thumb(p) and p not in self._pending]
        if not want:
            return
        self._pending.update(want)

        def done(error):
            self._pending.difference_update(want)
            if error:
                self.count.setText(error)
            self.grid.viewport().update()
            if self.stack.currentWidget() is self.viewer:
                self._show_image()

        engine.load_thumbs(want, done)

    # -- single image --

    @property
    def row(self) -> int:
        return self.grid.currentIndex().row()

    def open_image(self) -> None:
        if self.row >= 0:
            self.stack.setCurrentWidget(self.viewer)
            self._hints()
            self._show_image()

    def _show_image(self) -> None:
        path = self.model.paths[self.row]
        caption = f"{os.path.basename(path)}   ·   {num(self.row + 1)} of {num(len(self.model.paths))}"
        if path in self._previews:
            self.viewer.show_image(self._previews[path], True, caption)
            return
        self.viewer.show_image(self.win.engine.thumb(path), False, caption)
        self.win.engine.load_preview(path, self._preview_loaded)

    def _preview_loaded(self, path: str, image) -> None:
        self._previews[path] = image
        while len(self._previews) > 6:
            self._previews.popitem(last=False)
        if self.stack.currentWidget() is self.viewer and self.model.paths[self.row:self.row + 1] == [path]:
            self._show_image()

    def flip(self, step: int) -> None:
        row = min(max(self.row + step, 0), len(self.model.paths) - 1)
        if row != self.row:
            self.grid.setCurrentIndex(self.model.index(row))
            self.grid.scrollTo(self.model.index(row))
            self._show_image()

    # -- keys --

    def step_back(self) -> None:
        """Esc: image -> grid -> Classify."""
        if self.stack.currentWidget() is self.viewer:
            self.stack.setCurrentIndex(0)
            self._hints()
            self.grid.setFocus()
            self._lazy.start()
        else:
            self._token += 1
            self.win.go("classify")

    def classify(self, value: str) -> None:
        self._token += 1
        self.win.go("classify")
        self.win.pages["classify"].mark(value)

    def handle_key(self, event) -> bool:
        key = event.key()
        if event.modifiers() & ~Qt.KeypadModifier:
            return False
        viewing = self.stack.currentWidget() is self.viewer
        if key == Qt.Key_Escape:
            self.step_back()
        elif key == Qt.Key_P:
            self.classify(PERSONAL)
        elif key == Qt.Key_B:
            self.classify(BUSINESS)
        elif viewing and key in (Qt.Key_Left, Qt.Key_Right):
            self.flip(-1 if key == Qt.Key_Left else 1)
        elif viewing and (is_enter(event) or key in (Qt.Key_Up, Qt.Key_Down)):
            if is_enter(event):
                self.step_back()
        elif is_enter(event) and self.stack.currentIndex() == 0:
            self.open_image()
        else:
            return False
        return True
