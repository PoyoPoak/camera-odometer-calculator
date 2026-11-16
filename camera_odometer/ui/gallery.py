"""Gallery: lazy thumbnail grid of one folder, and the single-image view."""
from __future__ import annotations

import os
from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
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
    """One image, as large as the window allows. A click on its left or right third flips."""

    def __init__(self, flip):
        super().__init__()
        self.flip = flip
        self.image, self.sharp, self.caption = None, False, ""
        self.can = {-1: False, 0: False, 1: False}  # is there an image that way
        self.hover = 0  # the third under the mouse: -1 left, 1 right, 0 middle or away
        self.setMouseTracking(True)

    def show_image(self, image, sharp: bool, caption: str, back: bool = False, forward: bool = False) -> None:
        self.image, self.sharp, self.caption = image, sharp, caption
        self.can = {-1: back, 0: False, 1: forward}
        self._sync()

    def bar(self) -> int:
        """The side showing a flip bar: the hovered third, when there is an image that way."""
        return self.hover if self.can[self.hover] else 0

    def _sync(self) -> None:
        self.setCursor(Qt.PointingHandCursor if self.bar() else Qt.ArrowCursor)
        self.update()

    def _track(self, x: float) -> int:
        self.hover = -1 if x < self.width() / 3 else 1 if x > self.width() * 2 / 3 else 0
        self._sync()
        return self.hover

    def mouseMoveEvent(self, event):
        self._track(event.position().x())

    def enterEvent(self, event):  # opened under a still mouse: no move event comes
        self._track(event.position().x())

    def leaveEvent(self, _):
        self.hover = 0
        self._sync()

    def mousePressEvent(self, event):  # a double-click arrives here too, so quick clicks all flip
        if event.button() == Qt.LeftButton and self._track(event.position().x()):
            self.flip(self.hover)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#0b0b0c"))
        area = QRectF(self.rect()).adjusted(24, 20, -24, -52)
        if self.image is not None:
            p.drawImage(_fit(self.image, area), self.image)
        side = self.bar()
        if side:  # a soft glow from that edge with a chevron, fading toward the centre
            edge, w = (0 if side < 0 else self.width()), 110
            glow = QLinearGradient(edge, 0, edge - side * w, 0)
            glow.setColorAt(0, QColor(255, 255, 255, 34))
            glow.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(QRectF(min(edge, edge - side * w), 0, w, self.height()), glow)
            x, y = edge - side * 34, area.center().y()
            p.setPen(QPen(QColor(theme.TEXT), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(x - side * 7, y - 14), QPointF(x + side * 7, y), QPointF(x - side * 7, y + 14)])
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
        self.grid_keys = theme.legend((("←", "→", "↑", "↓"), "Move"), ("Enter", "Open"), ("P", "Personal"),
                                      ("B", "Business"), ("Esc", "Back"))
        self.image_keys = theme.legend((("←", "→"), "Flip"), ("P", "Personal"), ("B", "Business"), ("Esc", "Grid"))
        self.image_keys.hide()
        head.addWidget(self.grid_keys)
        head.addWidget(self.image_keys)
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
        self.viewer = Viewer(self.flip)
        self.stack = QStackedWidget()
        grid_wrap = QWidget()
        wrap = QVBoxLayout(grid_wrap)
        wrap.setContentsMargins(18, 12, 8, 0)
        wrap.addWidget(self.grid)
        for w in (grid_wrap, self.empty, self.viewer):
            self.stack.addWidget(w)
        self.stack.currentChanged.connect(self._hints)
        outer.addWidget(self.stack, 1)

        self._lazy = QTimer(self)
        self._lazy.setSingleShot(True)
        self._lazy.setInterval(60)  # one batch per pause in scrolling, not one per pixel
        self._lazy.timeout.connect(self._load_visible)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)  # a held arrow key must not queue a preview per image
        self._preview_timer.timeout.connect(self._load_preview)

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
        self.win.engine.run(lambda: self.win.list_images(path) if path else [],
                            lambda paths: token == self._token and self._listed(paths),
                            lambda message: token == self._token and self.empty.setText(message))

    def _listed(self, paths: list[str]) -> None:
        self.count.setText(f"{num(len(paths))} photo{'s' if len(paths) != 1 else ''}")
        if not paths:
            self.empty.setText("There are no photos from this year directly in this folder.\n"
                               "Press Esc to go back.")
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

    def _hints(self, _=0) -> None:
        """The hotkey legend of whichever view is showing."""
        viewing = self.stack.currentWidget() is self.viewer
        self.grid_keys.setVisible(not viewing)
        self.image_keys.setVisible(viewing)

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
            self._show_image()

    def _show_image(self) -> None:
        path = self.model.paths[self.row]
        caption = f"{os.path.basename(path)}   ·   {num(self.row + 1)} of {num(len(self.model.paths))}"
        sharp = path in self._previews
        self.viewer.show_image(self._previews[path] if sharp else self.win.engine.thumb(path), sharp, caption,
                               self.row > 0, self.row < len(self.model.paths) - 1)
        if not sharp:
            self._preview_timer.start()

    def _load_preview(self) -> None:
        if self.stack.currentWidget() is self.viewer and 0 <= self.row < len(self.model.paths):
            self.win.engine.load_preview(self.model.paths[self.row], self._preview_loaded)

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
