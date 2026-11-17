"""Genera assets/gigawalls.ico (varios tamaños) con el logo de GigaTech sobre una placa blanca redondeada.

Uso: python make_icon.py
"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size, logo):
    """Placa blanca redondeada con el logo centrado."""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    small = size <= 32  # en tamaños chicos el logo necesita más espacio para leerse
    margin = size * (0.02 if small else 0.03)
    plate = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    path = QPainterPath()
    path.addRoundedRect(plate, size * 0.20, size * 0.20)
    p.fillPath(path, QColor("white"))
    inner = size * (0.12 if small else 0.20)  # el logo ocupa ~76 % (chico) o ~60 % de la placa
    target = QRectF(inner, inner, size - 2 * inner, size - 2 * inner)
    p.drawImage(target, logo)
    p.end()
    return img


def png_bytes(img):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def write_ico(path, frames):
    """ICO con fotogramas PNG (formato admitido por Windows desde Vista)."""
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, blobs = b"", b""
    for size, data in frames:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    with open(path, "wb") as f:
        f.write(header + entries + blobs)


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 (necesario para QImage/QPainter)
    logo = QImage(os.path.join(ASSETS, "logo_icono.png"))
    if logo.isNull():
        raise SystemExit("Falta assets/logo_icono.png")
    frames = [(s, png_bytes(render(s, logo))) for s in SIZES]
    write_ico(os.path.join(ASSETS, "gigawalls.ico"), frames)
    render(256, logo).save(os.path.join(ASSETS, "gigawalls_256.png"))
    print("OK:", ", ".join(str(s) for s in SIZES))


if __name__ == "__main__":
    main()
