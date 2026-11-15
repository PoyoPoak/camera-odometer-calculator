"""Draw the app icon: an amber aperture on a dark tile, with an odometer strip at the larger sizes.

    python scripts/make_icon.py        (Windows Python with PySide6; the digits use Segoe UI)

Writes assets/icon.ico (16-256 px, every size drawn separately, not scaled down)
and build/icon-preview.png, a contact sheet for checking it by eye.
"""
import math
import os
import struct
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # never opens a window

from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter, QPen

ROOT = Path(__file__).resolve().parent.parent
SIZES = (16, 24, 32, 48, 64, 128, 256)
DARK, AMBER = QColor("#1c1c20"), QColor("#f5a524")


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size, size)  # draw in a 1 x 1 box from here on

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(DARK)
    p.drawRoundedRect(QRectF(0, 0, 1, 1), 0.2, 0.2)

    small = size < 48          # below 48 px: aperture only, heavier strokes
    cx, cy, radius = (0.5, 0.5, 0.34) if small else (0.5, 0.4, 0.27)
    stroke = (0.125 if size < 32 else 0.1) if small else 0.06
    pen = QPen(AMBER, stroke)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), radius, radius)

    # six blade edges: each runs along one side of the inner hexagon and on out to the ring
    inner = radius * (0.56 if size < 32 else 0.5)
    corner = lambda k: QPointF(cx + inner * math.cos(math.radians(60 * k - 15)),
                               cy + inner * math.sin(math.radians(60 * k - 15)))
    pen.setWidthF(stroke * (0.5 if size < 32 else 0.7))
    p.setPen(pen)
    for k in range(6):
        a, b = corner(k), corner(k + 1)
        reach = (math.sqrt(radius ** 2 - (inner * math.sqrt(3) / 2) ** 2) - inner / 2) / inner
        p.drawLine(a, b + (b - a) * reach)

    if not small:              # odometer: three digit wheels
        p.setPen(Qt.PenStyle.NoPen)
        font = QFont(FONT, weight=QFont.Weight.Bold)
        font.setPixelSize(max(1, round(size * 0.17)))
        for i, digit in enumerate("042"):
            cell = QRectF(0.19 + i * 0.215, 0.74, 0.19, 0.2)
            p.setBrush(AMBER)
            p.drawRoundedRect(cell, 0.03, 0.03)
            p.save()
            p.resetTransform()   # text in real pixels so the font hinting is right
            p.setFont(font)
            p.setPen(DARK)
            p.drawText(QRectF(cell.x() * size, cell.y() * size, cell.width() * size, cell.height() * size),
                       Qt.AlignmentFlag.AlignCenter, digit)
            p.restore()
    p.end()
    return image


def png(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def ico(images: list[QImage]) -> bytes:
    """ICO container holding one PNG per size (Qt itself only writes a single-size ICO)."""
    blobs = [png(i) for i in images]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = len(out) + 16 * len(images)
    for image, blob in zip(images, blobs):
        side = image.width() % 256  # 256 is stored as 0
        out += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    return out + b"".join(blobs)


if __name__ == "__main__":
    app = QGuiApplication([])
    # the offscreen platform starts with no fonts at all, so load one for the digits
    FONT = (QFontDatabase.applicationFontFamilies(
        QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\segoeuib.ttf")) or [""])[0]
    images = [draw(s) for s in SIZES]
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "icon.ico").write_bytes(ico(images))

    # contact sheet: every size at 1:1 on grey, then 16 / 24 / 32 enlarged without smoothing
    shown = images + [i.scaled(i.width() * 8, i.height() * 8) for i in images[:3]]
    sheet = QImage(sum(i.width() + 12 for i in shown) + 12, 280, QImage.Format.Format_RGB32)
    sheet.fill(QColor("#8a8a8a"))
    p, x = QPainter(sheet), 12
    for i in shown:
        p.drawImage(x, 12, i)
        x += i.width() + 12
    p.end()
    (ROOT / "build").mkdir(exist_ok=True)
    sheet.save(str(ROOT / "build" / "icon-preview.png"))
    print("wrote assets/icon.ico and build/icon-preview.png")
