"""Palette, stylesheet and the small formatting / painting helpers every page shares."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QLabel, QPushButton

from ..models import BUSINESS, PERSONAL

# One accent per meaning. Red is for warnings only.
PERSONAL_BLUE = "#5b9ff5"
BUSINESS_AMBER = "#f2a83a"
WARNING_RED = "#e8625a"
UNCLASSIFIED = "#7a7b84"
UNATTRIBUTED = "#3b3b42"

BG = "#111112"
SURFACE = "#19191b"
RAISED = "#232326"
HOVER = "#2c2c30"
BORDER = "#2b2b2f"
TEXT = "#ececed"
DIM = "#a3a3aa"
FAINT = "#6d6d75"

LABEL_COLOR = {BUSINESS: BUSINESS_AMBER, PERSONAL: PERSONAL_BLUE, None: UNCLASSIFIED}
LABEL_TEXT = {BUSINESS: "Business", PERSONAL: "Personal", None: "Unclassified"}

_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

QSS = f"""
QWidget {{ color: {TEXT}; font-size: 14px; }}
QMainWindow, QDialog, QWidget#page {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel[role="h1"] {{ font-size: 28px; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: 20px; font-weight: 600; }}
QLabel[role="dim"] {{ color: {DIM}; }}
QLabel[role="faint"] {{ color: {FAINT}; font-size: 13px; }}
QLabel[role="caps"] {{ color: {FAINT}; font-size: 11px; font-weight: 700; }}
QLabel[role="num"] {{ font-size: 34px; font-weight: 300; }}
QLabel[role="hero"] {{ font-size: 84px; font-weight: 300; }}
QLabel[role="error"] {{ color: {WARNING_RED}; background: rgba(232, 98, 90, 0.10);
    border: 1px solid rgba(232, 98, 90, 0.35); border-radius: 6px; padding: 10px 12px; }}
QLabel[role="badge"] {{ color: {DIM}; background: {RAISED}; border: 1px solid {BORDER};
    border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}

QPushButton {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 8px 16px; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:focus {{ border-color: #5c5c64; }}
QPushButton:disabled {{ color: {FAINT}; }}
QPushButton[kind="primary"] {{ background: {TEXT}; color: #111112; border: none;
    font-weight: 600; padding: 9px 22px; }}
QPushButton[kind="primary"]:hover {{ background: #ffffff; }}
QPushButton[kind="primary"]:disabled {{ background: #55555b; color: #1b1b1d; }}
QPushButton[kind="ghost"] {{ background: transparent; border: none; color: {DIM}; padding: 8px 10px; }}
QPushButton[kind="ghost"]:hover {{ color: {TEXT}; }}

QPushButton[kind="step"] {{ background: transparent; border: none; border-radius: 0;
    color: {FAINT}; padding: 0 4px; font-weight: 600; }}
QPushButton[kind="step"][state="done"] {{ color: {DIM}; }}
QPushButton[kind="step"][state="done"]:hover {{ color: {TEXT}; }}
QPushButton[kind="step"][state="current"] {{ color: {TEXT}; }}

QPushButton[kind="personal"], QPushButton[kind="business"] {{ font-size: 16px; font-weight: 700;
    padding: 0 22px; border-radius: 8px; min-height: 52px; min-width: 170px; }}
QPushButton[kind="personal"] {{ color: {PERSONAL_BLUE}; border: 1px solid rgba(91, 159, 245, 0.45);
    background: rgba(91, 159, 245, 0.08); }}
QPushButton[kind="personal"]:hover {{ background: rgba(91, 159, 245, 0.20); }}
QPushButton[kind="business"] {{ color: {BUSINESS_AMBER}; border: 1px solid rgba(242, 168, 58, 0.45);
    background: rgba(242, 168, 58, 0.08); }}
QPushButton[kind="business"]:hover {{ background: rgba(242, 168, 58, 0.20); }}

QLineEdit, QSpinBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 8px 10px; selection-background-color: #35527c; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: #5c5c64; }}
/* The stock arrows cannot be themed without image files: hidden, the page adds - / + buttons. */
QSpinBox {{ padding: 8px 4px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; height: 0; border: none; }}
QPushButton[kind="stepper"] {{ font-size: 18px; padding: 4px 0 7px 0; }}

QFrame[role="card"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame[role="folder"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; }}
QFrame[role="card"][flash="personal"] {{ border-color: {PERSONAL_BLUE}; background: #1b2434; }}
QFrame[role="card"][flash="business"] {{ border-color: {BUSINESS_AMBER}; background: #2c2416; }}
QFrame[role="card"][off="true"] {{ background: {BG}; }}
QFrame[role="bar"] {{ background: {SURFACE}; border: none; border-top: 1px solid {BORDER}; }}
QFrame[role="stepbar"] {{ background: {SURFACE}; border: none; border-bottom: 1px solid {BORDER}; }}
QFrame[role="banner"] {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame[role="line"] {{ background: {BORDER}; border: none; max-height: 1px; min-height: 1px; }}
QFrame[role="drop"] {{ background: {SURFACE}; border: 1px dashed #4a4a52; border-radius: 10px; }}
QFrame[role="drop"][active="true"] {{ border-color: {TEXT}; background: {RAISED}; }}

QProgressBar {{ background: {RAISED}; border: none; border-radius: 3px; max-height: 6px;
    min-height: 6px; }}
QProgressBar::chunk {{ background: {TEXT}; border-radius: 3px; }}

QScrollArea, QAbstractScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a3a41; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: #4b4b53; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3a3a41; border-radius: 3px; min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QTreeView, QListView, QTableView {{ background: transparent; border: none; outline: 0; }}
QListWidget#recent::item {{ border-radius: 6px; }}
QListWidget#recent::item:hover {{ background: {SURFACE}; }}
QListWidget#recent::item:selected {{ background: {RAISED}; }}
QTableView {{ gridline-color: transparent; selection-background-color: {RAISED};
    selection-color: {TEXT}; }}
QTableView::item {{ padding: 0 10px; border-bottom: 1px solid #1d1d20; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {BG}; color: {FAINT}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 8px 10px; font-size: 12px; font-weight: 600; }}
QHeaderView::section:hover {{ color: {TEXT}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}
"""


def apply(app: QApplication) -> None:
    """Fusion + dark palette under the stylesheet, so unstyled bits stay dark too."""
    if not QFontDatabase.families():
        # The offscreen platform (screenshot / selftest runs) starts with no fonts at all.
        for name in ("segoeui", "segoeuil", "seguisb", "segoeuib", "seguisym"):
            QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{name}.ttf")
    app.setStyle("Fusion")
    font = QFont(["Segoe UI Variable Text", "Segoe UI"])
    font.setPixelSize(14)
    app.setFont(font)
    pal = QPalette()
    for role, color in (
        (QPalette.Window, BG), (QPalette.Base, SURFACE), (QPalette.AlternateBase, RAISED),
        (QPalette.Button, RAISED), (QPalette.Text, TEXT), (QPalette.WindowText, TEXT),
        (QPalette.ButtonText, TEXT), (QPalette.Highlight, "#35527c"),
        (QPalette.HighlightedText, TEXT), (QPalette.ToolTipBase, RAISED),
        (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, FAINT),
    ):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    # The same icon as the exe: build.py bundles assets/ at the top of the frozen app.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    app.setWindowIcon(QIcon(str(base / "assets" / "icon.ico")))


# ---- formatting -----------------------------------------------------------

def num(n: int) -> str:
    return f"{n:,}"


def short_date(d: datetime | None, year: bool = False) -> str:
    if d is None:
        return "No date"
    return f"{_MONTHS[d.month - 1]} {d.day}" + (f", {d.year}" if year else "")


def date_range(a: datetime | None, b: datetime | None) -> str:
    if a is None or b is None:
        return short_date(a or b, year=True)
    if a.date() == b.date():
        return short_date(a, year=True)
    if a.year == b.year:
        return f"{short_date(a)} – {short_date(b, year=True)}"
    return f"{short_date(a, year=True)} – {short_date(b, year=True)}"


def camera_name(make: str, model: str) -> str:
    """"SONY" + "ILCE-7CM2" -> "Sony ILCE-7CM2"; "Canon" + "Canon EOS R5" stays as the model."""
    brand = make.split()[0] if make.split() else ""
    if not brand or model.lower().startswith(brand.lower()):
        return model or make or "Unknown camera"
    return f"{brand.capitalize() if brand.isupper() and len(brand) > 3 else brand} {model}"


def library_name(scan) -> str:
    """The selected photo folders by name: "Library + Studio"."""
    return " + ".join(os.path.basename(os.path.normpath(r)) or r for r in scan.roots)


# ---- widgets --------------------------------------------------------------

def label(text: str = "", role: str = "", **kw) -> QLabel:
    w = QLabel(text)
    if role:
        w.setProperty("role", role)
    if role == "caps":
        f = w.font()
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        w.setFont(f)
    if kw.get("wrap"):
        w.setWordWrap(True)
    if "align" in kw:
        w.setAlignment(kw["align"])
    return w


def button(text: str, kind: str = "", on_click=None, focus: bool = True) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    if not focus:
        b.setFocusPolicy(Qt.NoFocus)
    if on_click:
        b.clicked.connect(lambda _=False: on_click())
    return b


def frame(role: str) -> QFrame:
    f = QFrame()
    f.setProperty("role", role)
    return f


def restyle(w, **props) -> None:
    """Set dynamic properties and make the stylesheet notice."""
    for k, v in props.items():
        w.setProperty(k, v)
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class Check(QCheckBox):
    """Check box painted by hand: a stylesheet check mark would need an image file."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(0.5, (self.height() - 18) / 2 + 0.5, 18, 18)
        on = self.isChecked()
        p.setPen(QPen(QColor(TEXT if on or self.hasFocus() else "#5c5c64"), 1))
        p.setBrush(QColor(TEXT) if on else QColor(SURFACE))
        p.drawRoundedRect(box, 4, 4)
        if on:
            p.setPen(QPen(QColor(BG), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            x, y = box.x(), box.y()
            p.drawPolyline([QPointF(x + 4.5, y + 9.5), QPointF(x + 7.8, y + 12.6), QPointF(x + 13.5, y + 5.8)])
        p.setPen(QColor(TEXT if on else DIM))
        p.drawText(self.rect().adjusted(28, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())

