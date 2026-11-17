"""Detecta wallpapers repetidos en la búsqueda comparando sus miniaturas.

Varios sitios suben el mismo fondo con títulos distintos ("GTR3 Car" y "Blue Porsche 911" son la
misma imagen), y títulos parecidos no implican el mismo fondo ("Naruto Vs Sasuke" son tres
distintos), así que se compara la imagen con dos medidas que deben cumplirse a la vez:
- forma: correlación de la miniatura en gris (24x14, normalizada). Normalizar resalta el motivo, así
  dos fondos casi negros con distinto dibujo (Silver Surfer / agujero negro) no se confunden;
- color: promedio RGB en una cuadrícula de 4x4. Separa dos atardeceres distintos que en gris se
  parecen (degradado + sol).
Calibrado con ~50 parejas revisadas a ojo: los repetidos dan correlación >= 0.92 y color <= 16; los
distintos, correlación <= 0.68 cuando el color se parece, o color >= 32.
"""
import math

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage

_SIZE = QSize(300, 169)  # todas se llevan a 16:9 con recorte central, como se ven en la cuadrícula
_GRID_W, _GRID_H = 24, 14
MIN_SHAPE = 0.90  # correlación mínima (1 = idénticas)
MAX_COLOR = 20.0  # diferencia media por canal (0-255)


def fingerprint(image):
    """Huella (forma, colores) de una miniatura, o None si la imagen no sirve o es lisa."""
    if image.isNull():
        return None
    img = image.scaled(_SIZE, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    img = img.copy((img.width() - _SIZE.width()) // 2, (img.height() - _SIZE.height()) // 2,
                   _SIZE.width(), _SIZE.height())
    gray = img.convertToFormat(QImage.Format_Grayscale8).scaled(_GRID_W, _GRID_H, Qt.IgnoreAspectRatio,
                                                                Qt.SmoothTransformation)
    values = [gray.pixelColor(x, y).value() for y in range(_GRID_H) for x in range(_GRID_W)]
    mean = sum(values) / len(values)
    spread = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    if spread < 2:  # imagen lisa: no hay forma que comparar
        return None
    shape = tuple((v - mean) / spread for v in values)
    small = img.convertToFormat(QImage.Format_RGB32).scaled(4, 4, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    colors = tuple(v for y in range(4) for x in range(4)
                   for v in (lambda c: (c.red(), c.green(), c.blue()))(small.pixelColor(x, y)))
    return shape, colors


def same(a, b):
    """True si las dos huellas son del mismo wallpaper."""
    if sum(abs(x - y) for x, y in zip(a[1], b[1])) / len(a[1]) > MAX_COLOR:  # lo barato primero
        return False
    return sum(x * y for x, y in zip(a[0], b[0])) / len(a[0]) >= MIN_SHAPE
