"""Palette, stylesheet and the small formatting / painting helpers every page shares."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

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

/* Personal / Business toggles: tinted when that label is the folder's own, faint when inherited. */
QPushButton[kind="personal"], QPushButton[kind="business"] {{ font-weight: 700; padding: 6px 14px;
    border-radius: 6px; background: transparent; }}
QPushButton[kind="personal"] {{ color: {PERSONAL_BLUE}; border: 1px solid rgba(91, 159, 245, 0.35); }}
QPushButton[kind="personal"]:hover {{ background: rgba(91, 159, 245, 0.14); }}
QPushButton[kind="personal"][on="own"] {{ color: #0f1a2b; background: {PERSONAL_BLUE}; border-color: {PERSONAL_BLUE}; }}
QPushButton[kind="personal"][on="inherited"] {{ background: rgba(91, 159, 245, 0.16); }}
QPushButton[kind="business"] {{ color: {BUSINESS_AMBER}; border: 1px solid rgba(242, 168, 58, 0.35); }}
QPushButton[kind="business"]:hover {{ background: rgba(242, 168, 58, 0.14); }}
QPushButton[kind="business"][on="own"] {{ color: #2b1d08; background: {BUSINESS_AMBER}; border-color: {BUSINESS_AMBER}; }}
QPushButton[kind="business"][on="inherited"] {{ background: rgba(242, 168, 58, 0.16); }}

/* "Included Folders" in the step bar: a QPushButton with a QMenu, its stock arrow replaced by text. */
QPushButton[kind="menu"], QPushButton[kind="menu"]:hover, QPushButton[kind="menu"]:pressed {{
    background: transparent; border: none; color: {DIM}; padding: 6px 4px; }}
QPushButton[kind="menu"]:hover, QPushButton[kind="menu"]:pressed {{ color: {TEXT}; }}
QPushButton[kind="menu"]::menu-indicator {{ image: none; width: 0; }}
QMenu {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 8px 16px; border-radius: 5px; }}
QMenu::item:selected {{ background: {HOVER}; }}

/* A hotkey drawn as a key cap, so a legend never reads as a sentence. */
QLabel[role="key"] {{ color: {DIM}; background: {RAISED}; border: 1px solid #3a3a41;
    border-bottom: 2px solid #3a3a41; border-radius: 4px; padding: 0 6px; font-size: 12px;
    font-weight: 600; min-width: 10px; min-height: 18px; max-height: 18px; }}

QLineEdit, QSpinBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 8px 10px; selection-background-color: #35527c; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: #5c5c64; }}
/* The stock arrows cannot be themed without image files: hidden. Arrow keys and the wheel still step. */
QSpinBox {{ padding: 8px 4px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; height: 0; border: none; }}

QFrame[role="card"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame[role="folder"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; }}
QFrame[role="card"][off="true"] {{ background: {BG}; }}
/* An open area of the page with no card of its own, that still flashes a label colour. */
QFrame[role="pane"] {{ background: transparent; border: 1px solid transparent; border-radius: 10px; }}
QFrame[role="pane"][flash="personal"] {{ border-color: {PERSONAL_BLUE}; background: #1b2434; }}
QFrame[role="pane"][flash="business"] {{ border-color: {BUSINESS_AMBER}; background: #2c2416; }}
QFrame[role="bar"] {{ background: {SURFACE}; border: none; border-top: 1px solid {BORDER}; }}
QFrame[role="stepbar"] {{ background: {SURFACE}; border: none; border-bottom: 1px solid {BORDER}; }}
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


def legend(*items) -> QWidget:
    """Hotkey legend: one (keys, action) pair per item, keys a string or a tuple of them.
    Each key is drawn as a key cap and each action is capitalised: ("Esc", "Back")."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    for i, (keys, action) in enumerate(items):
        if i:
            row.addSpacing(22)
        for key in keys if isinstance(keys, tuple) else (keys,):
            row.addWidget(label(key, "key", align=Qt.AlignCenter))
            row.addSpacing(3)
        row.addSpacing(5)
        row.addWidget(label(action, "faint"))
    return w


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

    def hitButton(self, pos):  # the whole painted box (and text) takes clicks, not only the style's 14 px
        return self.rect().contains(pos)

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

