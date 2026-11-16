"""Results page: business-use percentage, breakdown bar, per-folder table and warnings."""
from __future__ import annotations

import os

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import calc
from . import theme
from .theme import LABEL_COLOR, LABEL_TEXT, button, label, num

SORT = Qt.UserRole


class StackedBar(QWidget):
    def __init__(self):
        super().__init__()
        self.parts: list[tuple[int, str]] = []
        self.setFixedHeight(18)

    def show_parts(self, parts: list[tuple[int, str]]) -> None:
        self.parts = parts
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 5, 5)
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor(theme.RAISED))
        total = sum(v for v, _ in self.parts)
        x = 0.0
        for value, color in self.parts:
            if not total or not value:
                continue
            w = self.width() * value / total
            p.fillRect(QRectF(x, 0, w, self.height()), QColor(color))
            if color == theme.UNATTRIBUTED:  # hatched, so it does not rely on colour alone
                p.fillRect(QRectF(x, 0, w, self.height()), QBrush(QColor("#5a5a63"), Qt.BDiagPattern))
            x += w
            p.fillRect(QRectF(x - 1, 0, 2, self.height()), QColor(theme.BG))  # thin separator


class SortItem(QTableWidgetItem):
    """Sorts by its SORT value, so "1,412" orders as a number."""

    def __lt__(self, other):
        return self.data(SORT) < other.data(SORT)


class ResultsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.summary = None
        col = QVBoxLayout(self)
        col.setContentsMargins(40, 24, 40, 20)
        col.setSpacing(0)

        top = QHBoxLayout()
        hero = QVBoxLayout()
        hero.setSpacing(0)
        hero.addWidget(label("BUSINESS USE", "caps"))
        self.pct = label("", "hero")
        self.pct.setContentsMargins(-4, -14, 0, -8)
        hero.addWidget(self.pct)
        self.sub = label("", "dim")
        hero.addWidget(self.sub)
        top.addLayout(hero, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.copy_button = button("Copy summary", on_click=self.copy_summary)
        actions.addWidget(self.copy_button)
        actions.addWidget(button("Export CSV…", "primary", self.export_csv))
        side = QVBoxLayout()
        side.addLayout(actions)
        side.addSpacing(8)
        side.addWidget(label("Labels are not saved when the app closes.\nExport the CSV to keep a record.",
                             "faint", align=Qt.AlignRight))
        side.addStretch(1)
        top.addLayout(side)
        col.addLayout(top)
        col.addSpacing(18)

        self.bar = StackedBar()
        col.addWidget(self.bar)
        col.addSpacing(10)
        self.legend = QHBoxLayout()
        self.legend.setSpacing(28)
        col.addLayout(self.legend)
        col.addSpacing(22)

        split = QHBoxLayout()
        split.setSpacing(24)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Folder", "Label", "Raw range", "Credited"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for c, w in ((1, 130), (2, 120), (3, 120)):
            header.setSectionResizeMode(c, QHeaderView.Fixed)
            self.table.setColumnWidth(c, w)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setHighlightSections(False)
        header.setSortIndicatorShown(True)
        for c in (2, 3):
            self.table.horizontalHeaderItem(c).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.horizontalHeaderItem(2).setToolTip("Shutter counts the folder spans, before overlaps are resolved")
        self.table.horizontalHeaderItem(3).setToolTip("Actuations credited to the folder after overlaps are resolved")
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setSortingEnabled(True)
        split.addWidget(self.table, 1)

        panel = theme.frame("card")
        panel.setFixedWidth(340)
        box = QVBoxLayout(panel)
        box.setContentsMargins(18, 16, 8, 12)
        box.setSpacing(10)
        self.warn_title = label("WARNINGS", "caps")
        box.addWidget(self.warn_title)
        self.warn_host = QWidget()
        self.warnings = QVBoxLayout(self.warn_host)
        self.warnings.setContentsMargins(0, 0, 10, 0)
        self.warnings.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.warn_host)
        scroll.setFocusPolicy(Qt.NoFocus)
        box.addWidget(scroll, 1)
        split.addWidget(panel)
        col.addLayout(split, 1)
        col.addSpacing(14)

        foot = QHBoxLayout()
        foot.addWidget(button("←  Back to folders", "ghost", win.back, focus=False))
        foot.addWidget(label("Esc", "faint"))
        foot.addStretch(1)
        self.note = label("", "faint")
        foot.addWidget(self.note)
        col.addLayout(foot)

    def enter(self):
        s = self.win.session
        scan = s.scan
        self.summary = sm = calc.summarize(scan, s.labels, s.excluded)
        included = [c for c in scan.cameras if c.id not in s.excluded]
        self.win.set_status(f"{theme.library_name(scan)} · {scan.year}")
        self.pct.setText(f"{sm.business_pct:.1f}%")
        n = len(included)
        self.sub.setText(f"{num(sm.business)} of {num(sm.year_total)} actuations in {scan.year}"
                         f" · {n} camera{'s' if n != 1 else ''}")
        open_rows = sum(r.label is None for r in sm.rows)
        self.note.setText(f"{num(open_rows)} folder{'s' if open_rows != 1 else ''} still unclassified: "
                          "not counted as business until labelled." if open_rows else "")

        parts = [("Business", sm.business, theme.BUSINESS_AMBER), ("Personal", sm.personal, theme.PERSONAL_BLUE),
                 ("Unclassified", sm.unclassified, theme.UNCLASSIFIED),
                 ("Unattributed", sm.unattributed, theme.UNATTRIBUTED)]
        self.bar.show_parts([(v, c) for _, v, c in parts])
        _clear(self.legend)
        for name, value, color in parts:
            pct = 100 * value / sm.year_total if sm.year_total else 0
            border = "#6a6a73" if color == theme.UNATTRIBUTED else color
            item = label(f'<span style="color:{border}">■</span>&nbsp; {name} &nbsp;'
                         f'<span style="color:{theme.DIM}">{num(value)} · {pct:.1f}%</span>')
            if name == "Unattributed":
                item.setToolTip("Shutter counts inside the year that are in no folder: deleted shots, "
                                "or albums stored somewhere else.")
            self.legend.addWidget(item)
        self.legend.addStretch(1)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(sm.rows))
        for i, row in enumerate(sm.rows):
            name = SortItem(row.rel.replace("/", "  ›  ") or "(top folder)")
            name.setData(SORT, row.rel.lower())
            name.setToolTip(row.rel)
            text = LABEL_TEXT[row.label]
            if row.label and row.rel not in s.labels:
                text += " (inherit)"
            lab = SortItem(text)
            lab.setData(SORT, text)
            lab.setForeground(QColor(LABEL_COLOR[row.label]))
            cells = [name, lab]
            for value in (row.raw, row.attributed):
                cell = SortItem(num(value))
                cell.setData(SORT, value)
                cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                cells.append(cell)
            for c, cell in enumerate(cells):
                self.table.setItem(i, c, cell)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)

        _clear(self.warnings)
        notes = list(sm.warnings) + [self._overlap_text(o) for o in sm.overlaps]
        self.warn_title.setText(f"WARNINGS · {len(notes)}" if notes else "WARNINGS")
        for text in notes:
            item = label(f'<span style="color:{theme.WARNING_RED}">●</span>&nbsp; {text}', wrap=True)
            item.setTextFormat(Qt.RichText)
            self.warnings.addWidget(item)
        if not notes:
            self.warnings.addWidget(label("Nothing to check. No overlapping folders or estimated cameras.",
                                          "dim", wrap=True))
        self.warnings.addStretch(1)

    def _overlap_text(self, o) -> str:
        cam = next((c for c in self.win.session.scan.cameras if c.id == o.camera_id), None)
        name = theme.camera_name(cam.make, cam.model) if cam else "One camera"
        a, b = (rel.rpartition("/")[2] or "(top folder)" for rel in (o.a, o.b))
        return (f"<b>Overlap</b>: “{a}” and “{b}” share {num(o.shared)} shutter counts on the {name}. "
                "They are credited to the folder with the narrower range.")

    def summary_text(self) -> str:
        s, sm = self.win.session, self.summary
        lines = [f"Camera Odometer: tax year {s.scan.year}",
                 *(f"Photo folder: {os.path.normpath(r)}" for r in s.scan.roots),
                 f"Business use: {sm.business_pct:.1f}%",
                 f"Year total: {num(sm.year_total)} actuations",
                 f"  Business: {num(sm.business)}",
                 f"  Personal: {num(sm.personal)}",
                 f"  Unclassified: {num(sm.unclassified)}",
                 f"  Unattributed: {num(sm.unattributed)}",
                 "Cameras:"]
        for c in s.scan.cameras:
            if c.id not in s.excluded:
                serial = f", serial {c.serial}" if c.serial else ""
                kind = "files (estimated)" if c.estimated else "actuations"
                lines.append(f"  {theme.camera_name(c.make, c.model)}{serial}: {num(c.actuations)} {kind}")
        return "\n".join(lines)

    def copy_summary(self):
        QGuiApplication.clipboard().setText(self.summary_text())
        self.win.unsaved = False
        self.copy_button.setText("Copied")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy summary"))

    def export_csv(self):
        s = self.win.session
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"camera-odometer-{s.scan.year}.csv",
                                              "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(calc.to_csv(s.scan, self.summary, s.excluded))
        except OSError as exc:
            self.win.set_status(f"Could not save the CSV: {exc.strerror or exc}")
        else:
            self.win.unsaved = False
            self.win.set_status(f"Saved {os.path.basename(path)}")

    def handle_key(self, event) -> bool:
        return False


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
