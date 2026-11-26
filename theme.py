"""Tema oscuro moderno (QSS) y utilidades visuales."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap

STYLE = """
* { font-family: 'Segoe UI Variable Text', 'Segoe UI'; font-size: 13px; color: #eef0f7; }
QMainWindow, QWidget#root { background: #171a26; }
QStatusBar { background: #171a26; color: #a2a9c2; padding: 4px 16px 6px 16px; }
QStatusBar::item { border: none; }

QFrame#sidebar { background: #1f2334; border-right: 1px solid #353c5a; }
QLabel#logo { font-size: 21px; font-weight: 700; color: #ffffff; }
QLabel#section { color: #a2a9c4; font-size: 11px; font-weight: 600; padding: 12px 8px 4px 8px; }
QLabel#nowplaying { color: #a2a9c2; padding: 4px 8px; }

QPushButton { background: #2a3046; border: 1px solid #363d58; border-radius: 10px;
              padding: 9px 16px; }
QPushButton:hover { background: #343b55; border-color: #454d6c; }
QPushButton:pressed { background: #252a3e; }
QPushButton:disabled { color: #5a607a; }
QPushButton#primary { background: #7c5cff; border: none; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #8f73ff; }
QPushButton#primary:pressed { background: #6a4be6; }
QPushButton#danger:hover { background: #3a1f2a; border-color: #6b2a3f; color: #ff7a93; }

QPushButton#chip { background: #343b55; border: 1px solid #454d70; border-radius: 14px;
                   padding: 7px 8px; font-size: 12px; color: #c8cde0; }
QPushButton#chip:hover { background: #342b6b; border-color: #7c5cff; color: white; }

QFrame#nowcard { background: #1a1e2e; border: 1px solid #353c5a; border-radius: 14px; }
QFrame#nowcard QLabel { background: transparent; }
QFrame#nowcard QLabel#section { padding: 0 2px 2px 2px; }
QFrame#nowcard QPushButton { padding: 7px 8px; }
QLabel#nowthumb { background: #12151f; border-radius: 10px; color: #8189a4; }
QLabel#nowtitle { color: #eef0f7; font-weight: 600; padding: 0 2px; }

QPushButton#toggle { padding: 10px 16px; }
QPushButton#toggle:checked { background: #3a3080; border-color: #7c5cff; color: #d6ccff; }
QPushButton#icon { padding: 6px 0; min-width: 34px; max-width: 34px; border-radius: 10px; }
QFrame#cardsep { background: #2e3450; border: none; }
QFrame#nowcard QLabel#section { padding: 0 2px; }
QFrame#nowcard QPushButton#link { background: transparent; border: none; padding: 2px 4px;
                                  color: #a996ff; font-size: 12px; font-weight: 600; }
QFrame#nowcard QPushButton#link:hover { color: #ffffff; }
QFrame#nowcard QPushButton#link:pressed { color: #7c5cff; }
QFrame#nowcard QComboBox#rotation[active="true"] { border-color: #7c5cff; background: #2b2657;
                                                   color: #d6ccff; }
QFrame#nowcard QComboBox { padding: 6px 10px; min-width: 0; border-radius: 10px; font-size: 12px; }
QLabel#libinfo { color: #9aa1ba; font-size: 12px; }
QLabel#previewnote { color: #a2a9c4; font-size: 14px; }
QDialog { background: #171a26; }

QPushButton#nav { background: transparent; border: none; text-align: left;
                  padding: 11px 14px; border-radius: 10px; color: #bcc2d6; }
QPushButton#nav:hover { background: #323957; color: white; }
QPushButton#nav:checked { background: #3a3080; color: #b9a8ff; font-weight: 600; }

QLineEdit { background: #20253a; border: 1px solid #363d58; border-radius: 12px;
            padding: 11px 16px; selection-background-color: #7c5cff; }
QLineEdit:focus { border-color: #7c5cff; }

QComboBox { background: #20253a; border: 1px solid #363d58; border-radius: 12px;
            padding: 10px 14px; min-width: 150px; }
QComboBox:hover { border-color: #454d6c; }
QComboBox:focus, QComboBox:on { border-color: #7c5cff; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: #20253a; border: 1px solid #363d58; border-radius: 8px;
                              padding: 4px; outline: none; selection-background-color: #342b6b; }

QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { background: #20253a; border: 2px solid transparent; border-radius: 14px;
                    padding: 8px; margin: 6px; color: #d8dcea; }
QListWidget::item:hover { background: #282e45; border-color: #434a69; }
QListWidget::item:selected { background: #2b2657; border-color: #7c5cff; color: white; }

QProgressBar { background: #2a3046; border: none; border-radius: 4px; height: 8px;
               text-align: center; color: transparent; }
QProgressBar::chunk { background: #7c5cff; border-radius: 4px; }

QCheckBox { spacing: 10px; color: #bcc2d6; padding: 4px 8px; }
QCheckBox::indicator { width: 36px; height: 20px; border-radius: 10px; background: #4a5272; }
QCheckBox::indicator:checked { background: #7c5cff; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #434a69; border-radius: 4px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: #56608a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QMenu { background: #20253a; border: 1px solid #363d58; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 20px; border-radius: 6px; }
QMenu::item:selected { background: #342b6b; }
QMessageBox { background: #20253a; }
"""


BADGE_COLORS = {"MoeWalls": "#e0508a", "DesktopHut": "#2a8ee6", "MotionBGS": "#e07b1f",
                "LiveWallpapers4Free": "#1f9e68"}


def badge(pixmap, text):
    """Dibuja una etiqueta con el nombre del origen en la esquina superior izquierda."""
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
    p.setBrush(QColor(BADGE_COLORS.get(text, "#7c5cff")))
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
