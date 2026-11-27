"""Tema oscuro moderno (QSS) y utilidades visuales."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap

STYLE = """
* { font-family: 'Nunito', 'Segoe UI'; font-size: 14px; color: #e6e8f0; }
QMainWindow, QWidget#root { background: #0f1117; }
QStatusBar { background: #0f1117; color: #8a90a6; padding: 4px 16px 6px 16px; }
QStatusBar::item { border: none; }

QFrame#sidebar { background: #1c2030; border-right: 1px solid #2c3249; }
QLabel#logo { font-size: 21px; font-weight: 700; color: #ffffff; }
QLabel#section { color: #8a90aa; font-size: 11px; font-weight: 600; padding: 12px 8px 4px 8px; }
QLabel#nowplaying { color: #8a90a6; padding: 4px 8px; }

QPushButton { background: #1d2130; border: 1px solid #272c3d; border-radius: 10px;
              padding: 9px 16px; }
QPushButton:hover { background: #262b3f; border-color: #343a52; }
QPushButton:pressed { background: #1a1e2c; }
QPushButton:disabled { color: #5a607a; }
QPushButton#primary { background: #7c5cff; border: none; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #8f73ff; }
QPushButton#primary:pressed { background: #6a4be6; }
QPushButton#danger:hover { background: #3a1f2a; border-color: #6b2a3f; color: #ff7a93; }

QPushButton#chip { background: #262b3f; border: 1px solid #343b57; border-radius: 14px;
                   padding: 7px 8px; font-size: 12px; color: #b4bad0; }
QPushButton#chip:hover { background: #251f4a; border-color: #7c5cff; color: white; }

QFrame#nowcard { background: #12151f; border: 1px solid #2c3249; border-radius: 14px; }
QFrame#nowcard QLabel { background: transparent; }
QFrame#nowcard QLabel#section { padding: 0 2px 2px 2px; }
QFrame#nowcard QPushButton { padding: 7px 8px; }
QLabel#nowthumb { background: #0b0d13; border-radius: 10px; color: #6b7189; }
QLabel#nowtitle { color: #e6e8f0; font-weight: 600; padding: 0 2px; }

QPushButton#toggle { padding: 10px 16px; }
QPushButton#toggle:checked { background: #2c2563; border-color: #7c5cff; color: #d6ccff; }
QPushButton#icon { padding: 6px 0; min-width: 34px; max-width: 34px; border-radius: 10px; }
QFrame#cardsep { background: #222839; border: none; }
QFrame#nowcard QLabel#section { padding: 0 2px; }
QFrame#nowcard QPushButton#link { background: transparent; border: none; padding: 2px 4px;
                                  color: #a996ff; font-size: 12px; font-weight: 600; }
QFrame#nowcard QPushButton#link:hover { color: #ffffff; }
QFrame#nowcard QPushButton#link:pressed { color: #7c5cff; }
QFrame#nowcard QComboBox#rotation[active="true"] { border-color: #7c5cff; background: #1d1a3a;
                                                   color: #d6ccff; }
QFrame#nowcard QComboBox { padding: 6px 10px; min-width: 0; border-radius: 10px; font-size: 12px; }
QLabel#libinfo { color: #7d849d; font-size: 12px; }
QLabel#previewnote { color: #8a90aa; font-size: 14px; }
QDialog { background: #0f1117; }

QPushButton#nav { background: transparent; border: none; text-align: left;
                  padding: 11px 14px; border-radius: 10px; color: #a3a9bf; }
QPushButton#nav:hover { background: #272c42; color: white; }
QPushButton#nav:checked { background: #2c2563; color: #b9a8ff; font-weight: 600; }

QLineEdit { background: #151821; border: 1px solid #272c3d; border-radius: 12px;
            padding: 11px 16px; selection-background-color: #7c5cff; }
QLineEdit:focus { border-color: #7c5cff; }

QComboBox { background: #151821; border: 1px solid #272c3d; border-radius: 12px;
            padding: 10px 14px; min-width: 150px; }
QComboBox:hover { border-color: #343a52; }
QComboBox:focus, QComboBox:on { border-color: #7c5cff; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: #151821; border: 1px solid #272c3d; border-radius: 8px;
                              padding: 4px; outline: none; selection-background-color: #251f4a; }

QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { background: #151821; border: 2px solid transparent; border-radius: 14px;
                    padding: 8px; margin: 6px; color: #c9cde0; }
QListWidget::item:hover { background: #1b1f2d; border-color: #2b3045; }
QListWidget::item:selected { background: #1d1a3a; border-color: #7c5cff; color: white; }

QProgressBar { background: #1d2130; border: none; border-radius: 4px; height: 8px;
               text-align: center; color: transparent; }
QProgressBar::chunk { background: #7c5cff; border-radius: 4px; }

QCheckBox { spacing: 10px; color: #a3a9bf; padding: 6px 8px; }
QCheckBox::indicator { width: 36px; height: 20px; border-radius: 10px; background: #383f5b; }
QCheckBox::indicator:checked { background: #7c5cff; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #2b3045; border-radius: 4px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: #3b4260; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QMenu { background: #151821; border: 1px solid #272c3d; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 20px; border-radius: 6px; }
QMenu::item:selected { background: #251f4a; }
QMessageBox { background: #151821; }

/* ---- Vida y tonos claros sobre el negro (1.2.1): las reglas de aquí abajo pisan a las de arriba ---- */
* { color: #eef0f7; }
QStatusBar { color: #a7adc4; }
QLabel#section { color: #b9a8ff; letter-spacing: 1px; }
QLabel#libinfo { color: #a3a9c0; }

/* barra lateral: brillo morado arriba que se funde en el negro */
QFrame#sidebar { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #241a4d, stop:0.35 #151728, stop:1 #10121b);
                 border-right: 1px solid #262a3d; }
QPushButton#nav { color: #c3c8da; }
QPushButton#nav:hover { background: #2a2650; color: #ffffff; }
QPushButton#nav:checked { background: #e9e3ff; color: #3b2a99; font-weight: 700; }
QPushButton#chip { background: #1f2336; border: 1px solid #353c5c; color: #d4d8e6; }
QPushButton#chip:hover { background: #e9e3ff; border-color: #e9e3ff; color: #3b2a99; }

/* tarjetas: superficie más clara que el fondo, con relieve y borde que se ve */
QListWidget::item { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #22263a, stop:1 #181b28);
                    border: 1px solid #2f3550; color: #e4e7f2; }
QListWidget::item:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b2852, stop:1 #1c1b33);
                          border-color: #7c5cff; color: #ffffff; }
QListWidget::item:selected { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a2f7a, stop:1 #221c48);
                             border: 2px solid #c9b8ff; color: #ffffff; }

/* «En tu escritorio» */
QFrame#nowcard { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d1a38, stop:1 #12141f);
                 border: 1px solid #3a3170; }
QLabel#nowtitle { color: #ffffff; }

/* botones */
QPushButton { background: #1f2333; border: 1px solid #333a55; color: #e8eaf3; }
QPushButton:hover { background: #2a2f47; border-color: #4a5278; color: #ffffff; }
QPushButton#primary { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c5cff, stop:1 #a64dff);
                      border: none; color: white; }
QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9479ff, stop:1 #bb6dff); }
QPushButton#toggle:checked { background: #e9e3ff; border-color: #e9e3ff; color: #3b2a99; font-weight: 600; }

/* cajas de texto y listas desplegables */
QLineEdit, QComboBox { background: #181b27; border: 1px solid #30364f; }
QLineEdit:focus, QComboBox:focus, QComboBox:on { border-color: #a78bff; background: #1c1a33; }

QCheckBox { color: #d0d4e4; }
QCheckBox::indicator { background: #3a4060; }
QCheckBox::indicator:checked { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c5cff, stop:1 #a64dff); }
QScrollBar::handle:vertical { background: #3a4060; }
QScrollBar::handle:vertical:hover { background: #7c5cff; }
QMenu::item:selected { background: #e9e3ff; color: #3b2a99; }

/* etiquetas de búsqueda rápida (barra lateral) */
QScrollArea#tagsarea, QWidget#tags { background: transparent; border: none; }
QPushButton#tag { background: #1a1d2b; border: 1px solid #333a58; border-radius: 14px; padding: 6px 4px;
                  color: #dfe2ee; font-weight: 600; font-size: 13px; }
QPushButton#tag:hover { background: #2a2650; border-color: #8f73ff; color: #ffffff; }
QPushButton#tag:checked { background: #e9e3ff; border-color: #e9e3ff; color: #3b2a99; }
"""


BADGE_COLORS = {"MoeWalls": "#e0508a", "DesktopHut": "#2a8ee6", "MotionBGS": "#e07b1f",
                "LiveWallpapers4Free": "#1f9e68"}


def badge(pixmap, text, color=None):
    """Dibuja una etiqueta (el nombre del origen, o la calidad del video) en la esquina superior izquierda."""
    out = QPixmap(pixmap)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    font = p.font()
    font.setPixelSize(11)
    font.setBold(True)
    p.setFont(font)
    w = p.fontMetrics().horizontalAdvance(text) + 16
    rect = QRectF(8, 8, w, 20)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color or BADGE_COLORS.get(text, "#7c5cff")))
    p.drawRoundedRect(rect, 10, 10)
    p.setPen(QColor("white"))
    p.drawText(rect, Qt.AlignCenter, text)
    p.end()
    return out


def rounded(pixmap, radius=10):
    """Devuelve el pixmap con las esquinas redondeadas."""
    out = QPixmap(pixmap.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(out.rect()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pixmap)
    p.end()
    return out
