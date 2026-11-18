"""GigaWalls - gestor de wallpapers animados con catalogos de MoeWalls y DesktopHut."""
import ctypes
import hashlib
import json
import os
import shutil
import sys
import tempfile
import winreg
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest

import cv2
from PySide6.QtCore import QObject, QRect, QRunnable, QSize, QSizeF, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGraphicsScene, QGraphicsView,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

import desktophut
import duplicados
import library
import livewallpapers4free
import moewalls
import motionbgs
import optimize
import traducir
from desktop import DesktopWallpaper
from instalacion import INSTALACION
from theme import STYLE, badge, rounded

SOURCES = {m.NAME: m for m in (moewalls, desktophut, motionbgs, livewallpapers4free)}
ALL_SOURCES = "Todos los orígenes"

FROZEN = getattr(sys, "frozen", False)  # True cuando corre como .exe empaquetado
# Ajustes junto al programa (portable). La biblioteca de videos va por defecto en Videos\GigaWalls,
# así es la misma esté el .exe donde esté (Release, portable\, desarrollo...).
ROOT = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
# Recursos empaquetados (iconos): dentro del .exe viven en la carpeta interna de PyInstaller.
RES = getattr(sys, "_MEIPASS", ROOT)
from PySide6.QtCore import QStandardPaths
LIBRARY = os.path.join(QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
                       or os.path.join(os.path.expanduser("~"), "Videos"), "GigaWalls")
THUMBS = os.path.join(LIBRARY, ".thumbs")
SETTINGS = os.path.join(ROOT, "settings.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DISPLAY_NAME = "GigaWalls"
APP_ID = "GigaTech.GigaWalls"  # identidad de Windows: agrupa la barra de tareas y usa nuestro icono
# Nombre interno (valor del registro de inicio y socket local). Se conserva para no romper el
# inicio automático que ya esté configurado.
APP_NAME = "AnimeWalls"
ASSETS = os.path.join(RES, "assets")
ICON_PATH = os.path.join(ASSETS, "gigawalls.ico")
ICON_SIZE = QSize(300, 169)
NOW_THUMB = QSize(206, 100)  # miniatura de la tarjeta "En tu escritorio"
# Accesos rápidos de la barra lateral: (texto visible, término que se busca en los sitios)
PREVIEW_DIR = os.path.join(tempfile.gettempdir(), "GigaWalls_previews")
# Opciones de rotación automática: (texto, minutos). 0 = sin rotar, -1 = al iniciar la app
ROTATIONS = (("No cambiar", 0), ("Cada 5 minutos", 5), ("Cada 15 minutos", 15),
             ("Cada 30 minutos", 30), ("Cada hora", 60), ("Cada vez que abro la app", -1))
EXPLORE = (("Anime", "anime"), ("Juegos", "game"), ("Cartoons", "cartoon"), ("Pixel art", "pixel art"),
           ("Paisajes", "landscape"), ("Lofi", "lofi"), ("Autos", "car"), ("Películas", "movie"))


_LIVE = set()


class _Signals(QObject):
    """Vive en el hilo principal: sus slots reenvian los callbacks a la interfaz."""
    done = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, on_done, on_error, on_progress, release):
        super().__init__()
        self._cb = (on_done, on_error, on_progress)
        self._release = release
        self.done.connect(self._on_done)
        self.error.connect(self._on_error)
        self.progress.connect(self._on_progress)

    def _on_done(self, result):
        try:
            if self._cb[0]:
                self._cb[0](result)
        finally:
            self._release()

    def _on_error(self, msg):
        try:
            if self._cb[1]:
                self._cb[1](msg)
        finally:
            self._release()

    def _on_progress(self, done, total):
        if self._cb[2]:
            self._cb[2](done, total)


class Worker(QRunnable):
    """Ejecuta fn en un hilo; fn recibe un callback progress(done, total)."""

    def __init__(self, fn, on_done=None, on_error=None, on_progress=None):
        super().__init__()
        self.fn = fn
        self.setAutoDelete(False)
        _LIVE.add(self)  # vivo hasta que su resultado se entregue en el hilo principal
        self.signals = _Signals(on_done, on_error, on_progress, lambda: _LIVE.discard(self))

    def run(self):
        try:
            result = self.fn(self.signals.progress.emit)
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))
        else:
            self.signals.done.emit(result)


def draw_spinner(p, rect, angle, width=3):
    """Arco giratorio del color de la marca sobre un aro tenue (indicador de 'trabajando')."""
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 30), width))
    p.drawEllipse(rect)
    pen = QPen(QColor("#7c5cff"), width)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawArc(rect, -angle * 16, 100 * 16)


class Spinner(QWidget):
    """Ruedita que gira mientras está visible (el temporizador solo corre mientras se ve)."""

    def __init__(self, size=16):
        super().__init__()
        self.setFixedSize(size, size)
        self.angle = 0
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self.angle = (self.angle + 6) % 360
        self.update()

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        draw_spinner(p, QRect(2, 2, self.width() - 4, self.height() - 4), self.angle, 2)
        p.end()


class _Grid(QListWidget):
    """Cuadrícula de tarjetas que reparte el ancho disponible entre las columnas que caben."""
    MIN_CELL = ICON_SIZE.width() + 36
    CELL_H = ICON_SIZE.height() + 50

    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setIconSize(ICON_SIZE)
        self.setGridSize(QSize(self.MIN_CELL, self.CELL_H))
        self.setWordWrap(True)
        self.setUniformItemSizes(True)
        # Aviso grande en el centro mientras la cuadrícula está vacía ("Buscando…", "Sin resultados")
        self._notice, self._notice_sub, self._notice_spin = "", "", False
        self._spin_angle = 0
        self._spin_timer = QTimer(self, interval=16)
        self._spin_timer.timeout.connect(self._spin_tick)

    def set_notice(self, text="", sub="", spinning=False):
        """Texto centrado que se ve solo mientras no hay tarjetas; con ruedita si está trabajando."""
        self._notice, self._notice_sub, self._notice_spin = text, sub, spinning
        if spinning:
            self._spin_timer.start()
        else:
            self._spin_timer.stop()
        self.viewport().update()

    def _spin_tick(self):
        self._spin_angle = (self._spin_angle + 6) % 360
        if self.count() == 0:
            self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() or not self._notice:
            return
        p = QPainter(self.viewport())
        r = self.viewport().rect()
        y = r.height() // 2 - 50
        if self._notice_spin:
            draw_spinner(p, QRect(r.width() // 2 - 22, y - 22, 44, 44), self._spin_angle, 4)
            y += 40
        font = p.font()
        font.setPixelSize(17)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#e6e8f0"))
        p.drawText(QRect(0, y, r.width(), 28), Qt.AlignCenter, self._notice)
        if self._notice_sub:
            font.setPixelSize(13)
            font.setBold(False)
            p.setFont(font)
            p.setPen(QColor("#8a90a6"))
            p.drawText(QRect(0, y + 30, r.width(), 22), Qt.AlignCenter, self._notice_sub)
        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # se reserva siempre el hueco de la barra de scroll para que el reparto no cambie al aparecer
        avail = self.width() - 2 * self.frameWidth() - self.verticalScrollBar().sizeHint().width() - 8
        cols = max(1, avail // self.MIN_CELL)
        cell = QSize(avail // cols, self.CELL_H)
        if cell != self.gridSize():
            self.setGridSize(cell)
            for i in range(self.count()):
                self.item(i).setSizeHint(cell)


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8-sig") as f:  # -sig: tolera la marca BOM de algunos editores
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def search_sources(names, query, page):
    """Busca en varios orígenes a la vez y mezcla los resultados (uno de cada origen por turno).

    Devuelve (items, errores). Solo lanza excepción si fallaron todos y no hay nada que mostrar.
    """
    def one(name):
        try:
            return name, SOURCES[name].search(query, page), None
        except Exception as e:  # noqa: BLE001
            return name, [], f"{name}: {e}"

    with ThreadPoolExecutor(max_workers=len(names)) as ex:
        results = list(ex.map(one, names))
    errors = [err for _, _, err in results if err]
    lists = [items for _, items, _ in results]
    merged = [it for group in zip_longest(*lists) for it in group if it is not None]
    if errors and not merged:
        raise RuntimeError("; ".join(errors))
    return merged, errors


def make_thumb(video_path):
    os.makedirs(THUMBS, exist_ok=True)
    thumb = os.path.join(THUMBS, os.path.basename(video_path) + ".jpg")
    if not os.path.exists(thumb):
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
        ok, frame = cap.read()
        cap.release()
        if ok:
            frame = cv2.resize(frame, (ICON_SIZE.width(), ICON_SIZE.height()))
            cv2.imwrite(thumb, frame)
    return thumb if os.path.exists(thumb) else None


def fetch_preview(info):
    """Descarga (o reutiliza de la caché temporal) la vista previa y devuelve su ruta local."""
    source = SOURCES[info["source"]]
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    path = os.path.join(PREVIEW_DIR, hashlib.sha1(info["url"].encode()).hexdigest()[:16] + source.PREVIEW_EXT)
    if not os.path.exists(path):
        tmp = path + ".part"
        source.download_preview(info["url"], tmp)
        os.replace(tmp, path)
    return path


class _MirrorVideo(QGraphicsView):
    """Muestra el video y lo puede voltear en vivo (espejo izq<->der y/o arriba<->abajo) en la GPU,
    para ver cómo quedará el fondo reflejado antes de descargarlo."""

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsVideoItem()  # conserva la proporción dentro del tamaño que se le da
        self.scene().addItem(self.item)
        self.setFrameShape(QFrame.NoFrame)
        self.setBackgroundBrush(QColor("black"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._h = self._v = False

    def set_mirror(self, h, v):
        self._h, self._v = h, v
        self._fit()

    def _fit(self):
        w, h = self.viewport().width(), self.viewport().height()
        self.item.setSize(QSizeF(w, h))
        self.item.setTransform(QTransform().translate(w if self._h else 0, h if self._v else 0)
                               .scale(-1 if self._h else 1, -1 if self._v else 1))
        self.setSceneRect(0, 0, w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class PreviewDialog(QDialog):
    """Reproduce un clip corto del wallpaper antes de decidir si descargarlo. Se puede reflejar y
    descargarlo ya reflejado. on_download(use, modes): modes es '', 'h', 'v' o 'hv'."""

    def __init__(self, parent, info, on_download):
        super().__init__(parent)
        self._alive = True
        self.player = None
        self.setWindowTitle(info["title"])
        self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(760, 520)
        set_dark_title_bar(int(self.winId()))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 16)
        lay.setSpacing(12)
        head = QLabel(f"{info['title']}  ·  {info['source']}", objectName="nowtitle")
        head.setWordWrap(True)
        lay.addWidget(head)
        self.video = _MirrorVideo()
        self.video.setMinimumSize(640, 360)
        self.video.hide()
        self.note = QLabel("Cargando vista previa...", objectName="previewnote")
        self.note.setAlignment(Qt.AlignCenter)
        self.note.setMinimumHeight(360)
        lay.addWidget(self.video, 1)
        lay.addWidget(self.note, 1)
        row = QHBoxLayout()
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        self.flip_h = QPushButton("Reflejar ↔", objectName="toggle", checkable=True)
        self.flip_v = QPushButton("Reflejar ↕", objectName="toggle", checkable=True)
        self.flip_h.setToolTip("Voltear izquierda ↔ derecha: se descarga ya reflejado")
        self.flip_v.setToolTip("Voltear arriba ↕ abajo: se descarga ya reflejado")
        for b in (self.flip_h, self.flip_v):
            b.toggled.connect(lambda _on: self.video.set_mirror(self.flip_h.isChecked(), self.flip_v.isChecked()))
        dl = QPushButton("Descargar")
        dl.clicked.connect(lambda: (self.accept(), on_download(False, self.modes())))
        use = QPushButton("Descargar y usar como fondo", objectName="primary")
        use.clicked.connect(lambda: (self.accept(), on_download(True, self.modes())))
        row.addWidget(close)
        row.addSpacing(12)
        row.addWidget(self.flip_h)
        row.addWidget(self.flip_v)
        row.addStretch()
        row.addWidget(dl)
        row.addWidget(use)
        lay.addLayout(row)

    def modes(self):
        return ("h" if self.flip_h.isChecked() else "") + ("v" if self.flip_v.isChecked() else "")

    def show_clip(self, path):
        if not self._alive:
            return
        self.player = QMediaPlayer(self)
        audio = QAudioOutput(self)
        audio.setMuted(True)
        self.player.setAudioOutput(audio)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.player.setVideoOutput(self.video.item)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.note.hide()
        self.video.show()
        self.player.play()

    def show_error(self, msg):
        if self._alive:
            self.note.setText(f"No se pudo cargar la vista previa.\n{msg}")

    def done(self, result):
        self._alive = False
        if self.player:  # soltar el archivo y el decodificador
            self.player.stop()
            self.player.setVideoOutput(None)
            self.player.setSource(QUrl())
            self.player.deleteLater()
            self.player = None
        super().done(result)


class MainWindow(QMainWindow):
    def __init__(self, wallpaper, settings):
        super().__init__()
        self.wallpaper = wallpaper
        self.settings = settings
        self.pool = QThreadPool.globalInstance()
        self.query = ""
        self._busy = False  # una sola descarga/conversión a la vez
        self._gen = 0  # identifica la búsqueda en curso
        self.exhausted = False
        self.page = 0
        self.loading = False
        self.setWindowTitle(DISPLAY_NAME)
        self.setWindowIcon(QIcon(ICON_PATH))
        set_dark_title_bar(int(self.winId()))
        self.resize(1240, 820)
        self.setMinimumSize(1000, 780)  # por debajo, la barra lateral no cabe
        self.setAcceptDrops(True)  # arrastrar videos a la ventana para importarlos
        self.rotation_timer = QTimer(self)
        self.rotation_timer.timeout.connect(lambda: self.next_wallpaper(auto=True))

        root = QWidget(objectName="root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_search_tab())
        self.pages.addWidget(self._build_library_tab())
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.status = self.statusBar()
        # barra de progreso compartida por todas las pestañas (descargar, optimizar, reflejar)
        self.progress = QProgressBar()
        self.progress.setFixedSize(280, 10)
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.status.addPermanentWidget(self.progress)

        self._build_tray()
        self._update_now_playing()
        self._apply_rotation()
        self.search("")

    # ---------- barra lateral ----------
    def _build_sidebar(self):
        bar = QFrame(objectName="sidebar")
        bar.setFixedWidth(250)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(12, 18, 12, 14)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 4, 8, 18)
        brand.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(QPixmap(os.path.join(ASSETS, "logo_negativo.png"))
                       .scaledToHeight(30, Qt.SmoothTransformation))
        name = QLabel('Giga<span style="color:#7ac70c">Walls</span>', objectName="logo")
        brand.addWidget(mark)
        brand.addWidget(name)
        brand.addStretch()
        lay.addLayout(brand)
        group = QButtonGroup(self)
        for i, text in enumerate(("🌐  Catálogo", "🎞  Mi biblioteca")):
            b = QPushButton(text, objectName="nav", checkable=True)
            b.setChecked(i == 0)
            group.addButton(b, i)
            lay.addWidget(b)
        group.idClicked.connect(self._goto_page)
        self.nav_group = group

        lay.addWidget(QLabel("EXPLORAR", objectName="section"))
        chips = QGridLayout()
        chips.setContentsMargins(8, 0, 8, 0)
        chips.setSpacing(6)
        for i, (label, term) in enumerate(EXPLORE):
            chip = QPushButton(label, objectName="chip")
            chip.clicked.connect(lambda _=False, t=term: self._explore(t))
            chips.addWidget(chip, i // 2, i % 2)
        lay.addLayout(chips)
        lay.addStretch()

        card = QFrame(objectName="nowcard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 10, 10, 10)
        cl.setSpacing(8)
        cl.addWidget(QLabel("EN TU ESCRITORIO", objectName="section"))
        self.now_thumb = QLabel(objectName="nowthumb")
        self.now_thumb.setFixedSize(NOW_THUMB)
        self.now_thumb.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.now_thumb, 0, Qt.AlignHCenter)
        self.now_title = QLabel(objectName="nowtitle")
        self.now_title.setWordWrap(True)
        cl.addWidget(self.now_title)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.pause_btn = QPushButton("Pausar")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.stop_btn = QPushButton("Quitar", objectName="danger")
        self.stop_btn.clicked.connect(self.stop_wallpaper)
        buttons.addWidget(self.pause_btn)
        buttons.addWidget(self.stop_btn)
        cl.addLayout(buttons)
        sep = QFrame(objectName="cardsep")
        sep.setFixedHeight(1)
        cl.addSpacing(2)
        cl.addWidget(sep)
        head = QHBoxLayout()
        head.setSpacing(4)
        head.addWidget(QLabel("CAMBIAR DE FONDO", objectName="section"))
        head.addStretch()
        self.next_btn = QPushButton("Siguiente ›", objectName="link")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setToolTip("Pasa ya a otro fondo al azar")
        self.next_btn.clicked.connect(lambda: self.next_wallpaper())
        head.addWidget(self.next_btn)
        cl.addLayout(head)
        self.rotation_box = QComboBox(objectName="rotation")
        for text, minutes in ROTATIONS:
            self.rotation_box.addItem(text, minutes)
        self.rotation_box.setToolTip("Cambia de fondo solo. Rota entre tus favoritos (si tienes 2 o más) "
                                     "o, si no, entre toda la biblioteca")
        saved = self.settings.get("rotation", 0)
        self.rotation_box.setCurrentIndex(max(0, self.rotation_box.findData(saved)))
        self.rotation_box.currentIndexChanged.connect(self._on_rotation_changed)
        cl.addWidget(self.rotation_box)
        self._mark_rotation()
        lay.addWidget(card)
        lay.addSpacing(6)

        self.all_screens = QCheckBox("Video en todas las pantallas")
        self.all_screens.setChecked(self.settings.get("all_screens", False))
        self.all_screens.setToolTip("Desmarcado: el video solo se reproduce en la pantalla principal "
                                    "y las demás muestran una imagen fija (usa mucha menos GPU)")
        self.all_screens.toggled.connect(self._set_all_screens)
        lay.addWidget(self.all_screens)
        self.pause_covered = QCheckBox("Pausar si lo tapan")
        self.pause_covered.setChecked(self.settings.get("pause_when_covered", True))
        self.pause_covered.setToolTip("Pausa el fondo cuando ventanas maximizadas o un juego a "
                                      "pantalla completa lo tapan (ahorra GPU)")
        self.pause_covered.toggled.connect(self._set_pause_covered)
        lay.addWidget(self.pause_covered)
        self.eco = QCheckBox("Modo ahorro (720p/24)")
        self.eco.setChecked(self.settings.get("eco", False))
        self.eco.setToolTip("Al descargar, importar u optimizar, deja los videos en 720p y 24 fps: "
                            "gasta ~20 % menos GPU (medido) y pesa 3 veces menos.\n"
                            "No cambia los videos que ya tienes; usa 'Optimizar' en la biblioteca.")
        self.eco.toggled.connect(self._set_eco)
        lay.addWidget(self.eco)
        self.autostart = QCheckBox("Abrir al encender la PC")
        self.autostart.setToolTip("Abre GigaWalls en la bandeja al iniciar sesión en Windows para que tu "
                                  "fondo animado vuelva solo.\nSin esto, tras reiniciar queda el fondo normal "
                                  "de Windows hasta que abras la app.")
        self.autostart.setChecked(self._autostart_enabled())
        self.autostart.toggled.connect(self._set_autostart)
        lay.addWidget(self.autostart)
        return bar

    def _set_pause_covered(self, on):
        self.settings["pause_when_covered"] = on
        save_settings(self.settings)
        self.wallpaper.pause_when_covered = on

    def _set_eco(self, on):
        self.settings["eco"] = on
        save_settings(self.settings)

    # ---------- rotación ----------
    def _on_rotation_changed(self, _index):
        minutes = self.rotation_box.currentData()
        self.settings["rotation"] = minutes
        save_settings(self.settings)
        self._apply_rotation()
        self._mark_rotation()
        if minutes > 0:
            self.status.showMessage(f"El fondo cambiará cada {minutes} min", 5000)
        elif minutes < 0:
            self.status.showMessage("El fondo cambiará cada vez que abras la app", 5000)

    def _mark_rotation(self):
        """Resalta el selector cuando la rotación está activa."""
        box = self.rotation_box
        box.setProperty("active", box.currentData() != 0)
        box.style().unpolish(box)
        box.style().polish(box)

    def _apply_rotation(self):
        self.rotation_timer.stop()
        minutes = self.settings.get("rotation", 0)
        if minutes > 0:
            self.rotation_timer.start(minutes * 60 * 1000)

    def next_wallpaper(self, auto=False):
        """Cambia a otro video al azar (favoritos si hay 2 o más; si no, toda la biblioteca)."""
        if auto and self._busy:  # no cambiar a mitad de una conversión
            return
        paths = library.videos(LIBRARY)
        choice = library.pick_next(paths, self.settings.get("favorites", []), self.settings.get("current"))
        if not choice:
            self.status.showMessage("No hay videos en la biblioteca", 4000)
        elif choice != self.settings.get("current"):
            self.set_wallpaper(choice)
        elif not auto:
            self.status.showMessage("Solo hay un video para rotar", 4000)

    def _set_all_screens(self, on):
        self.settings["all_screens"] = on
        save_settings(self.settings)
        self.wallpaper.all_screens = on
        current = self.settings.get("current")
        if current and os.path.exists(current):
            self.wallpaper.set_video(current)

    def _goto_page(self, index):
        self.pages.setCurrentIndex(index)
        if index == 1:
            self.refresh_library()

    def _explore(self, term):
        """Acceso rápido de la barra lateral: abre el catálogo y busca esa categoría."""
        self.nav_group.button(0).setChecked(True)
        self._goto_page(0)
        self.search_box.setText(term)
        self.search(term)

    # ---------- catalogo ----------
    def _build_search_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 22, 24, 16)
        lay.setSpacing(14)
        row = QHBoxLayout()
        self.search_box = QLineEdit(placeholderText="Buscar en español o inglés: atardecer en la playa, coche rojo, naruto...")
        self.search_box.returnPressed.connect(lambda: self.search(self.search_box.text().strip()))
        self.source_box = QComboBox()
        self.source_box.addItems([ALL_SOURCES, *SOURCES])
        self.source_box.setCurrentText(self.settings.get("source", ALL_SOURCES))
        self.source_box.currentTextChanged.connect(self._on_source_changed)
        btn = QPushButton("Buscar", objectName="primary")
        btn.clicked.connect(lambda: self.search(self.search_box.text().strip()))
        row.addWidget(self.search_box)
        row.addWidget(self.source_box)
        row.addWidget(btn)
        lay.addLayout(row)

        self.results = self._make_grid()
        self.results.itemDoubleClicked.connect(self.preview)  # ver antes de descargar
        self.results.verticalScrollBar().valueChanged.connect(self._maybe_load_more)
        lay.addWidget(self.results)

        row = QHBoxLayout()
        hint = QLabel("Doble clic para ver una vista previa", objectName="libinfo")
        prev = QPushButton("Vista previa")
        prev.clicked.connect(lambda: self.preview(self.results.currentItem()))
        dl = QPushButton("Descargar")
        dl.clicked.connect(lambda: self.download(self.results.currentItem(), use=False))
        use = QPushButton("Descargar y usar como fondo", objectName="primary")
        use.clicked.connect(lambda: self.download(self.results.currentItem(), use=True))
        # Indicador de búsqueda en curso (también al cargar más páginas, con tarjetas ya visibles)
        self.busy_spin = Spinner(18)
        self.busy_label = QLabel()
        self.busy_label.setStyleSheet("color: #a993ff; font-size: 13px;")
        self.busy_spin.hide()
        self.busy_label.hide()
        row.addWidget(hint)
        row.addSpacing(16)
        row.addWidget(self.busy_spin)
        row.addWidget(self.busy_label)
        row.addStretch()
        row.addWidget(prev)
        row.addWidget(dl)
        row.addWidget(use)
        lay.addLayout(row)
        return w

    def _make_grid(self):
        return _Grid()

    def _on_source_changed(self, name):
        self.settings["source"] = name
        save_settings(self.settings)
        self.search(self.search_box.text().strip())

    def _selected_sources(self):
        name = self.source_box.currentText()
        return list(SOURCES) if name == ALL_SOURCES else [name]

    def search(self, query):
        self.query = query
        self.page = 0
        self.exhausted = False
        self._gen += 1  # descarta resultados de busquedas anteriores que sigan en vuelo
        self.loading = False
        self.results.clear()
        self._urls = set()  # el mismo wallpaper listado dos veces (el sitio corrió sus páginas)
        self._fingerprints = []  # huellas de las miniaturas ya mostradas (ver duplicados.py)
        self._hidden = 0
        self._note = ""  # parte fija del mensaje de estado (traducción, orígenes que fallaron)
        self.load_more()

    def load_more(self):
        if self.loading or self.exhausted:
            return
        self.loading = True
        self.page += 1
        gen, page, query, names = self._gen, self.page, self.query, self._selected_sources()
        self._search_status("Buscando...")
        self._search_busy(page, names)

        def job(_p):
            english = traducir.to_english(query)  # los sitios solo entienden inglés
            return (*search_sources(names, english, page), english)
        self.pool.start(Worker(job, lambda result: self._on_results(*result, gen),
                               lambda msg: self._on_search_error(msg, gen)))

    def _search_busy(self, page, names=None):
        """Muestra (o con page=None oculta) el indicador de búsqueda: abajo junto a los botones
        siempre, y grande en el centro mientras todavía no hay ninguna tarjeta."""
        on = page is not None
        self.busy_spin.setVisible(on)
        self.busy_label.setVisible(on)
        if not on:
            return
        what = "Buscando…" if page == 1 else f"Cargando más… (página {page})"
        sources = f"en {names[0]}" if len(names) == 1 else f"en {len(names)} sitios a la vez"
        self.busy_label.setText(f"{what}  {sources}")
        title = f"Buscando “{self.query}”…" if self.query else "Cargando lo más nuevo…"
        self.results.set_notice(title, sources.capitalize(), spinning=True)

    def _search_status(self, msg, ms=0):
        """Los mensajes de la búsqueda solo se muestran en el catálogo: no pisan los de otras pestañas."""
        if self.pages.currentIndex() == 0:
            self.status.showMessage(msg, ms)

    def _maybe_load_more(self, *_):
        """Carga la siguiente página al acercarse al final (o si la actual no llena la ventana)."""
        # Con la ventana oculta/minimizada (arranque con --minimized o en la bandeja) la lista no tiene
        # tamaño, la barra de scroll queda en 0 y esto cargaba paginas y miniaturas sin fin: la RAM
        # crecia ~8 MB/s (6 GB en una hora). Solo se carga mas cuando la ventana se ve.
        if not self.isVisible() or self.isMinimized():
            return
        bar = self.results.verticalScrollBar()
        if bar.maximum() - bar.value() < 400:
            self.load_more()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(500, self._maybe_load_more)  # al abrir, completa la lista si no llena la ventana

    def _on_search_error(self, msg, gen):
        if gen != self._gen:
            return
        self.loading = False
        self.page -= 1  # para poder reintentar la misma página
        self._search_status(f"Error al buscar: {msg}")
        self._search_busy(None)
        self.results.set_notice("No se pudo buscar", msg if len(msg) < 140 else msg[:137] + "…")

    def _on_results(self, items, errors, english, gen):
        if gen != self._gen:
            return
        self.loading = False
        if not items:
            self.exhausted = True
        note = ""
        if english != self.query:
            note += f"  ·  buscado en inglés: «{english}»" if english else "  ·  mostrando lo más nuevo"
        if errors:  # un origen falló pero el otro respondió
            note += f"  ·  sin respuesta de {', '.join(e.split(':')[0] for e in errors)}"
        self._note = note
        self._search_busy(None)
        if not items:
            self._search_status("No hay más resultados" + note, 5000)
            self.results.set_notice("Sin resultados", "Prueba con otras palabras u otro origen")
        for it in items:
            if it["url"] in self._urls:
                continue
            self._urls.add(it["url"])
            item = QListWidgetItem(it["title"])
            item.setData(Qt.UserRole, it)
            item.setSizeHint(self.results.gridSize())
            self.results.addItem(item)
            self.pool.start(Worker(lambda _p, it=it: SOURCES[it["source"]].get_thumb(it["thumb"]),
                                   lambda data, i=item, it=it: self._set_thumb(i, data, it, gen)))
        if items:
            self._show_count(8000 if errors else 5000)
        QTimer.singleShot(500, self._maybe_load_more)

    def _show_count(self, ms=5000):
        shown = self.results.count() - self._hidden
        msg = f"{shown} resultados"
        if self._hidden:
            msg += f"  ·  {self._hidden} repetido{'s' if self._hidden > 1 else ''} oculto{'s' if self._hidden > 1 else ''}"
        self._search_status(msg + self._note, ms)

    def _set_thumb(self, item, data, info, gen):
        pm = QPixmap()
        try:
            if not pm.loadFromData(data):
                return
            cover = pm.scaled(ICON_SIZE, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            cover = cover.copy(0, 0, ICON_SIZE.width(), ICON_SIZE.height())
            item.setIcon(QIcon(rounded(badge(cover, info["source"]))))
        except RuntimeError:  # el item ya no existe (se hizo otra busqueda)
            return
        if gen != self._gen or "nsfw" in info["thumb"]:
            # DesktopHut pone la misma imagen genérica a todo su contenido adulto: no son repetidos
            return
        fp = duplicados.fingerprint(pm.toImage())
        if fp is None:
            return
        if any(duplicados.same(fp, other) for other in self._fingerprints):
            # el mismo fondo subido a otro sitio (o con otro título): se deja el que llegó primero
            item.setHidden(True)
            self._hidden += 1
            self._show_count()
            QTimer.singleShot(0, self._maybe_load_more)  # lo oculto deja hueco: completar la vista
        else:
            self._fingerprints.append(fp)

    def preview(self, item):
        """Abre una ventana con un clip corto del wallpaper (1-3 MB) antes de descargarlo."""
        if item is None:
            self.status.showMessage("Selecciona un wallpaper primero", 3000)
            return
        info = item.data(Qt.UserRole)
        dlg = PreviewDialog(self, info, lambda use, modes: self.download_info(info, use, modes))
        self.pool.start(Worker(lambda _p: fetch_preview(info), dlg.show_clip, dlg.show_error))
        dlg.exec()
        dlg.deleteLater()

    def download(self, item, use):
        if item is None:
            self.status.showMessage("Selecciona un wallpaper primero", 3000)
            return
        self.download_info(item.data(Qt.UserRole), use)

    def download_info(self, info, use, modes=""):
        """modes: '' sin reflejar, o 'h' / 'v' / 'hv' para guardarlo ya reflejado."""
        source = SOURCES[info["source"]]
        os.makedirs(LIBRARY, exist_ok=True)
        dest = os.path.join(LIBRARY, source.filename(info["url"]))
        final = optimize.flipped_name(dest, modes) if modes else dest
        if os.path.exists(final):
            if use:
                self.set_wallpaper(final)
            else:
                self.status.showMessage("Ya está en tu biblioteca", 5000)
            return
        if not self._begin(f"Descargando {info['title']}..."):
            return

        self.pool.start(Worker(
            lambda progress: source.download(info["url"], dest, progress),
            lambda _r: self._on_downloaded(dest, use, modes),
            self._on_download_error,
            lambda d, t: self.progress.setValue(int(d * 100 / t) if t else 0)))

    def _begin(self, message):
        """Reserva el 'turno' de trabajo y muestra la barra. False si ya hay una operación en curso."""
        if self._busy:
            self.status.showMessage("Espera: hay otra operación en curso", 4000)
            return False
        self._busy = True
        self.progress.setValue(0)
        self.progress.show()
        self.status.showMessage(message)
        return True

    def _end(self):
        self._busy = False
        self.progress.hide()

    def _on_download_error(self, msg):
        self._end()
        self.status.showMessage(f"Error de descarga: {msg}")

    def _on_downloaded(self, dest, use, modes=""):
        if not modes:
            self._optimize(dest, lambda: self.set_wallpaper(dest) if use else None)
            return
        # reflejar y optimizar en una sola conversión; el original sin reflejar no se guarda
        eco = self.settings.get("eco", False)
        self.progress.setValue(0)
        self.status.showMessage("Reflejando y optimizando...")

        def done(out):
            self._end()
            self.refresh_library()
            self.status.showMessage("Listo y reflejado", 6000)
            if use:
                self.set_wallpaper(out)

        def failed(err):  # queda el original descargado, sin reflejar
            self._end()
            self.refresh_library()
            self.status.showMessage(f"No se pudo reflejar ({err}); quedó el original en tu biblioteca", 8000)
            if use:
                self.set_wallpaper(dest)

        self.pool.start(Worker(
            lambda progress: optimize.optimize_flipped(dest, modes, progress, eco), done, failed,
            lambda d, t: self.progress.setValue(int(d * 100 / t) if t else 0)))

    def _optimize(self, path, then):
        """Convierte al perfil elegido (1080p/30 o ahorro 720p/24) si hace falta y luego llama a then()."""
        eco = self.settings.get("eco", False)
        self.progress.setValue(0)
        self.status.showMessage("Optimizando a 720p/24fps (modo ahorro)..." if eco
                                else "Optimizando a 1080p/30fps para ahorrar GPU...")

        def finish(msg):
            self._end()
            self.status.showMessage(msg, 6000)
            then()

        self.pool.start(Worker(
            lambda progress: optimize.optimize(path, progress, eco),
            lambda converted: finish("Listo y optimizado" if converted else "Listo"),
            lambda err: finish(f"No se pudo optimizar ({err}); se usa el original"),
            lambda d, t: self.progress.setValue(int(d * 100 / t) if t else 0)))

    def flip_wallpaper(self, path, mode):
        """Crea una copia reflejada en la biblioteca y la aplica como fondo."""
        if not self._begin("Reflejando video..."):
            return

        def done(out):
            self._end()
            self.refresh_library()
            self.set_wallpaper(out)

        def failed(err):
            self._end()
            self.status.showMessage(f"No se pudo reflejar: {err}")

        self.pool.start(Worker(
            lambda progress: optimize.flip(path, mode, progress), done, failed,
            lambda d, t: self.progress.setValue(int(d * 100 / t) if t else 0)))

    def optimize_wallpaper(self, path):
        if not self._begin("Optimizando..."):
            return
        was_current = self.settings.get("current") == path
        if was_current:
            self.wallpaper.stop()  # Windows no deja reemplazar un archivo que se esta reproduciendo
        self._optimize(path, lambda: (self.set_wallpaper(path) if was_current else None,
                                      self.refresh_library()))

    # ---------- biblioteca ----------
    def _build_library_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 22, 24, 16)
        lay.setSpacing(14)

        top = QHBoxLayout()
        self.lib_filter = QLineEdit(placeholderText="Filtrar tu biblioteca...")
        self.lib_filter.textChanged.connect(lambda _: self.refresh_library())
        self.fav_only = QPushButton("★ Favoritos", objectName="toggle", checkable=True)
        self.fav_only.setToolTip("Mostrar solo tus favoritos")
        self.fav_only.toggled.connect(lambda _: self.refresh_library())
        top.addWidget(self.lib_filter, 1)
        top.addWidget(self.fav_only)
        lay.addLayout(top)

        self.library = self._make_grid()
        self.library.itemDoubleClicked.connect(lambda it: self.set_wallpaper(it.data(Qt.UserRole)))
        lay.addWidget(self.library)
        self.lib_info = QLabel(objectName="libinfo")
        lay.addWidget(self.lib_info)

        row = QHBoxLayout()
        tools = QPushButton("Herramientas")
        menu = QMenu(tools)
        menu.addAction("Abrir carpeta", lambda: (os.makedirs(LIBRARY, exist_ok=True), os.startfile(LIBRARY)))
        menu.addAction("Optimizar el seleccionado (ahorra GPU)",
                       lambda: self._lib_action(self.optimize_wallpaper))
        menu.addAction("Importar videos...", self._pick_files_to_import)
        menu.addSeparator()
        menu.addAction("Limpiar reflejados y duplicados...", self.clean_library)
        tools.setMenu(menu)
        fav = QPushButton("★ Favorito")
        fav.setToolTip("Marcar o desmarcar el video seleccionado como favorito")
        fav.clicked.connect(lambda: self._lib_action(self.toggle_favorite))
        flip = QPushButton("Reflejar ↔")
        flip.clicked.connect(lambda: self._lib_action(lambda p: self.flip_wallpaper(p, "h")))
        delete = QPushButton("Eliminar", objectName="danger")
        delete.clicked.connect(lambda: self._lib_action(self.delete_wallpaper))
        use = QPushButton("Usar como fondo", objectName="primary")
        use.clicked.connect(lambda: self._lib_action(self.set_wallpaper))
        for b in (tools, fav, flip):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(delete)
        row.addWidget(use)
        lay.addLayout(row)
        return w

    def refresh_library(self):
        previous = self.library.currentItem().data(Qt.UserRole) if self.library.currentItem() else None
        self.library.clear()
        paths = library.videos(LIBRARY)
        favs = set(self.settings.get("favorites", []))
        text = self.lib_filter.text().strip().lower()
        shown = [p for p in paths
                 if (not self.fav_only.isChecked() or os.path.basename(p) in favs)
                 and text in library.display_name(p).lower()]
        shown.sort(key=lambda p: (os.path.basename(p) not in favs, os.path.basename(p)))  # favoritos primero
        for path in shown:
            star = "★ " if os.path.basename(path) in favs else ""
            item = QListWidgetItem(star + library.display_name(path))
            item.setData(Qt.UserRole, path)
            item.setSizeHint(self.library.gridSize())
            thumb = make_thumb(path)
            if thumb:
                item.setIcon(QIcon(rounded(QPixmap(thumb))))
            self.library.addItem(item)
            if path == previous:
                self.library.setCurrentItem(item)
        n_favs = sum(1 for p in paths if os.path.basename(p) in favs)
        info = f"{len(paths)} videos · {library.human(library.total_size(paths))} · {n_favs} favoritos"
        if len(shown) != len(paths):
            info = f"Mostrando {len(shown)} de {info}"
        self.lib_info.setText(info + "   ·   Arrastra videos a la ventana para importarlos")

    def _lib_action(self, fn):
        item = self.library.currentItem()
        if item:
            fn(item.data(Qt.UserRole))
        else:
            self.status.showMessage("Selecciona un video de la biblioteca primero", 3000)

    def toggle_favorite(self, path):
        name = os.path.basename(path)
        favs = list(self.settings.get("favorites", []))
        if name in favs:
            favs.remove(name)
        else:
            favs.append(name)
        self.settings["favorites"] = favs
        save_settings(self.settings)
        self.refresh_library()

    def _forget(self, path):
        """Quita un video borrado de los favoritos."""
        favs = [f for f in self.settings.get("favorites", []) if f != os.path.basename(path)]
        self.settings["favorites"] = favs

    def delete_wallpaper(self, path):
        if QMessageBox.question(self, "Eliminar", f"¿Borrar {os.path.basename(path)}?") != QMessageBox.Yes:
            return
        if self.settings.get("current") == path:
            self.stop_wallpaper()  # Windows no deja borrar un video que se está reproduciendo
        os.remove(path)
        self._forget(path)
        save_settings(self.settings)
        self.refresh_library()

    def clean_library(self):
        """Borra los reflejados y duplicados, protegiendo el fondo actual y los favoritos."""
        paths = library.videos(LIBRARY)
        favs = {p for p in paths if os.path.basename(p) in set(self.settings.get("favorites", []))}
        keep = favs | {self.settings.get("current")}
        found = library.cleanup_candidates(paths, keep)
        if not found:
            QMessageBox.information(self, "Limpiar biblioteca",
                                    "No hay reflejados ni duplicados que borrar.")
            return
        freed = library.total_size([p for p, _ in found])
        box = QMessageBox(self)
        box.setWindowTitle("Limpiar biblioteca")
        box.setText(f"Se borrarán {len(found)} archivos y se liberarán {library.human(freed)}.")
        box.setInformativeText("No se tocan tus favoritos ni el fondo actual. "
                               "Los reflejados se pueden volver a generar.")
        box.setDetailedText("\n".join(f"{os.path.basename(p)}  —  {why}  ({library.human(os.path.getsize(p))})"
                                      for p, why in found))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        if box.exec() != QMessageBox.Yes:
            return
        failed = 0
        for path, _ in found:
            try:
                os.remove(path)
                self._forget(path)
            except OSError:
                failed += 1
        save_settings(self.settings)
        self.refresh_library()
        self.status.showMessage(f"Biblioteca limpia: {library.human(freed)} liberados"
                                + (f" ({failed} no se pudieron borrar)" if failed else ""), 8000)

    # ---------- importar videos propios ----------
    def _pick_files_to_import(self):
        from PySide6.QtWidgets import QFileDialog
        exts = " ".join(f"*{e}" for e in library.VIDEO_EXTS)
        files, _ = QFileDialog.getOpenFileNames(self, "Importar videos", "", f"Videos ({exts})")
        if files:
            self.import_files(files)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.import_files([u.toLocalFile() for u in event.mimeData().urls()])

    def import_files(self, files):
        """Copia los videos a la biblioteca y los deja listos (mp4, 1080p/30 o ahorro)."""
        files = [f for f in files if os.path.isfile(f) and f.lower().endswith(library.VIDEO_EXTS)]
        if not files:
            self.status.showMessage(f"Solo se pueden importar videos ({', '.join(library.VIDEO_EXTS)})", 5000)
            return
        if not self._begin(f"Importando {len(files)} video(s)..."):
            return
        eco = self.settings.get("eco", False)
        os.makedirs(LIBRARY, exist_ok=True)

        def job(progress):
            done = []
            for i, src in enumerate(files):
                if os.path.dirname(os.path.abspath(src)) == os.path.abspath(LIBRARY):
                    done.append(src)  # ya está en la biblioteca
                    continue
                dest = library.unique_dest(LIBRARY, os.path.basename(src))
                shutil.copy2(src, dest)
                done.append(optimize.normalize(
                    dest, lambda d, t, i=i: progress(i * 1000 + int(1000 * d / t), len(files) * 1000), eco))
            return done

        def finished(done):
            self._end()
            self.nav_group.button(1).setChecked(True)
            self._goto_page(1)
            self.status.showMessage(f"{len(done)} video(s) importado(s)", 6000)
            for i in range(self.library.count()):  # dejar seleccionado el último importado
                if self.library.item(i).data(Qt.UserRole) == done[-1]:
                    self.library.setCurrentRow(i)

        def failed(err):
            self._end()
            self.refresh_library()
            self.status.showMessage(f"No se pudo importar: {err}", 8000)

        self.pool.start(Worker(job, finished, failed,
                               lambda d, t: self.progress.setValue(int(d * 100 / t) if t else 0)))

    # ---------- fondo ----------
    def set_wallpaper(self, path):
        self.wallpaper.set_video(path)
        self.settings["current"] = path
        save_settings(self.settings)
        self._update_now_playing()
        self.status.showMessage("Fondo aplicado", 5000)
        self.ensure_profile(path)

    def ensure_profile(self, path):
        """Si el fondo supera el perfil elegido (bajado antes de activar el modo ahorro, una copia
        reflejada...) se convierte en segundo plano mientras se sigue viendo, y al terminar se cambia
        por la versión ligera. Un video más grande que el perfil pide un buffer enorme por fotograma:
        con la memoria del PC al límite, esa reserva falla y Qt cierra el programa (crash del 11/11)."""
        if self._busy:  # hay otra operación: se revisa la próxima vez que se aplique
            return
        self._busy = True  # se reserva sin mostrar nada: casi siempre el video ya cumple el perfil
        eco = self.settings.get("eco", False)

        def progress(d, t):
            if self.progress.isHidden():
                self.progress.show()
                self.status.showMessage("Optimizando el fondo en segundo plano (gasta menos memoria)...")
            self.progress.setValue(int(d * 100 / t) if t else 0)

        def converted(tmp):
            if not tmp:
                self._end()
                return
            playing = self.settings.get("current") == path
            paused = self.wallpaper.paused
            if playing:
                self.wallpaper.stop()  # Windows no deja reemplazar un archivo que se está reproduciendo

            def swapped(_r):
                self._end()
                restart()
                self.refresh_library()
                self.status.showMessage("Fondo optimizado", 6000)

            def swap_failed(err):
                self._end()
                restart()
                self.status.showMessage(f"No se pudo optimizar el fondo ({err}); se usa el original", 8000)

            def restart():
                if playing and self.settings.get("current") == path:
                    self.wallpaper.set_video(path)
                    if paused:
                        self.wallpaper.toggle_pause()

            # el reproductor suelta el archivo al procesar su deleteLater: se espera un poco
            QTimer.singleShot(500, lambda: self.pool.start(
                Worker(lambda _p: optimize.replace(tmp, path), swapped, swap_failed)))

        def failed(err):
            self._end()
            self.status.showMessage(f"No se pudo optimizar el fondo ({err}); se usa el original", 8000)

        self.pool.start(Worker(lambda p: optimize.convert(path, p, eco), converted, failed, progress))

    def stop_wallpaper(self):
        self.wallpaper.stop()
        self.settings.pop("current", None)
        save_settings(self.settings)
        self._update_now_playing()

    def _update_now_playing(self):
        """Refresca la tarjeta 'En tu escritorio' de la barra lateral."""
        current = self.settings.get("current")
        thumb = make_thumb(current) if current and os.path.exists(current) else None
        if thumb:
            cover = QPixmap(thumb).scaled(NOW_THUMB, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            cover = cover.copy((cover.width() - NOW_THUMB.width()) // 2, 0, NOW_THUMB.width(), NOW_THUMB.height())
            self.now_thumb.setPixmap(rounded(cover))
            self.now_title.setText(os.path.splitext(os.path.basename(current))[0].replace("-", " ").title())
        else:
            self.now_thumb.clear()
            self.now_thumb.setText("Sin fondo animado")
            self.now_title.setText("Elige uno del catálogo\no de tu biblioteca")
        self.pause_btn.setEnabled(bool(thumb))
        self.stop_btn.setEnabled(bool(thumb))
        self._sync_pause_ui()

    def _sync_pause_ui(self):
        text = "Reanudar" if self.wallpaper.paused else "Pausar"
        self.pause_btn.setText(text)
        if hasattr(self, "pause_action"):
            self.pause_action.setText(text)

    # ---------- bandeja / inicio ----------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(QIcon(ICON_PATH), self)
        self.tray.setToolTip(DISPLAY_NAME)
        menu = QMenu()
        show = QAction(f"Abrir {DISPLAY_NAME}", self)
        show.triggered.connect(self.show_window)
        self.pause_action = QAction("Pausar", self)
        self.pause_action.triggered.connect(self._toggle_pause)
        next_action = QAction("Siguiente fondo", self)
        next_action.triggered.connect(lambda: self.next_wallpaper())
        quit_ = QAction("Salir", self)
        quit_.triggered.connect(self._quit)
        for a in (show, self.pause_action, next_action):
            menu.addAction(a)
        menu.addSeparator()
        novedades = QAction("Novedades…", self)
        novedades.triggered.connect(INSTALACION.ver_novedades)
        menu.addAction(novedades)
        if INSTALACION.corriendo_instalada:  # solo si es la copia instalada
            uninstall = QAction("Desinstalar de esta PC…", self)
            uninstall.triggered.connect(self._uninstall)
            menu.addAction(uninstall)
        menu.addSeparator()
        menu.addAction(quit_)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show_window() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def _toggle_pause(self):
        self.wallpaper.toggle_pause()
        self._sync_pause_ui()

    def show_window(self):
        self.showNormal()
        self.activateWindow()

    def _quit(self):
        self.pool.waitForDone(3000)
        self.wallpaper.stop()
        self.tray.hide()
        QApplication.processEvents()  # deja que se liberen reproductor y widgets antes de salir
        QApplication.quit()

    def _uninstall(self):
        if INSTALACION.desinstalar(
                f"Los videos de tu biblioteca ({LIBRARY}) no se borran.", limpiar=self.wallpaper.stop):
            self.tray.hide()
            os._exit(0)  # ya se quitó todo: no guardar ajustes de nuevo

    def closeEvent(self, event):  # cerrar = minimizar a la bandeja
        event.ignore()
        self.hide()
        self.tray.showMessage(DISPLAY_NAME, "Sigue en la bandeja del sistema.",
                              QSystemTrayIcon.Information, 2000)

    @staticmethod
    def _autostart_enabled():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except OSError:
            return False

    @staticmethod
    def _set_autostart(on):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except OSError:
                    pass


def launch_command():
    """Comando que arranca esta copia de la app (para el inicio con Windows)."""
    if FROZEN:
        return f'"{sys.executable}" --minimized'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw}" "{os.path.join(ROOT, "main.py")}" --minimized'


def refresh_autostart():
    """Si el inicio con Windows está activo pero apunta a otra ruta (la carpeta se movió o se copió
    a otro PC), lo reapunta a esta copia. Si hay una copia instalada, esa manda: una portable no la pisa.
    También borra entradas de arranque duplicadas de versiones antiguas (p. ej. «GigaTech GigaWalls» sin
    --minimized), que abrían una segunda copia con la ventana visible al encender la PC."""
    if INSTALACION.instalada and not INSTALACION.corriendo_instalada:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
            stale, i = [], 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                i += 1
                if name != APP_NAME and isinstance(value, str) and                         os.path.basename(value.split('"')[1] if value.startswith('"') else value.split()[0]
                                         ).lower() == "gigawalls.exe":
                    stale.append(name)
            for name in stale:
                winreg.DeleteValue(k, name)
            if winreg.QueryValueEx(k, APP_NAME)[0] != launch_command():
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, launch_command())
    except (OSError, IndexError):
        pass  # no está activado


def selftest(out_path, video=None):
    """Comprueba que el .exe empaquetado trae todo lo necesario. Escribe un informe en out_path.
    Con `video`, además reproduce ese archivo unos segundos para verificar la decodificación."""
    import subprocess
    import requests.certs
    from PySide6.QtCore import QEventLoop, QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
    lines, ok_all = [], True

    def playback():
        player = QMediaPlayer()
        player.setAudioOutput(QAudioOutput())
        sink = QVideoSink()  # recibe los fotogramas decodificados, igual que el fondo del escritorio
        frames = []
        sink.videoFrameChanged.connect(lambda f: frames.append(f.isValid()))
        player.setVideoSink(sink)
        player.setSource(QUrl.fromLocalFile(video))
        player.play()
        loop = QEventLoop()
        QTimer.singleShot(4000, loop.quit)
        loop.exec()
        if player.error() != QMediaPlayer.NoError or player.position() <= 0 or sum(frames) < 20:
            raise RuntimeError(f"{player.mediaStatus().name}, pos={player.position()}, "
                               f"fotogramas={sum(frames)}, {player.errorString()}")
        return f"{sum(frames)} fotogramas decodificados en 4 s, avanzó hasta {player.position()} ms"

    def check(name, fn):
        nonlocal ok_all
        try:
            lines.append(f"OK     {name}: {fn()}")
        except Exception as e:  # noqa: BLE001
            ok_all = False
            lines.append(f"FALLA  {name}: {type(e).__name__}: {e}")

    def ffmpeg():
        exe = optimize.imageio_ffmpeg.get_ffmpeg_exe()
        out = subprocess.run([exe, "-version"], capture_output=True, text=True,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        return out.stdout.splitlines()[0][:40]

    def writable():
        os.makedirs(LIBRARY, exist_ok=True)
        probe = os.path.join(LIBRARY, ".probe")
        open(probe, "w").close()
        os.remove(probe)
        return LIBRARY

    def need(path):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        return "existe"

    check("ffmpeg", ffmpeg)
    check("opencv", lambda: cv2.__version__)
    check("QtMultimedia", lambda: type(QMediaPlayer()).__name__)
    check("certificados HTTPS", lambda: need(requests.certs.where()))
    check("icono", lambda: need(ICON_PATH))
    check("logo", lambda: need(os.path.join(ASSETS, "logo_negativo.png")))
    check("carpeta de datos escribible", writable)
    if video:
        check("reproducir video", playback)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + f"\nRESULTADO: {'TODO OK' if ok_all else 'HAY FALLOS'}\n")
    return 0 if ok_all else 1


def already_running():
    """Si ya hay una instancia devuelve True y, salvo en un arranque con Windows (--minimized), le
    pide que muestre su ventana."""
    sock = QLocalSocket()
    sock.connectToServer(APP_NAME)
    if sock.waitForConnected(300):
        if "--minimized" not in sys.argv:
            sock.write(b"show")
            sock.waitForBytesWritten(300)
        return True
    return False


def set_dark_title_bar(hwnd):
    """Barra de título oscura (Windows 10 20H1+ / 11). Si no se puede, queda la clara."""
    try:
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), 20, ctypes.byref(value), ctypes.sizeof(value))  # DWMWA_USE_IMMERSIVE_DARK_MODE
    except OSError:
        pass


CRASH_LOG = os.path.join(ROOT, "crash.log")
_crash_file = None  # abierto todo el rato: faulthandler escribe en él justo cuando el proceso muere


def enable_crash_log():
    """Guarda en crash.log (junto al programa) lo que haga caer la app: errores fatales de Qt (qFatal,
    falta de memoria...), la pila de Python de todos los hilos si el proceso aborta o hay una
    violación de acceso, y las excepciones de Python no controladas. Así un crash dice qué pasó sin
    tener que analizar volcados de memoria."""
    global _crash_file
    import datetime
    import faulthandler
    import traceback
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    try:
        if os.path.getsize(CRASH_LOG) > 512 * 1024:  # no dejar que crezca sin límite
            with open(CRASH_LOG, "rb") as f:
                f.seek(-128 * 1024, os.SEEK_END)
                tail = f.read()
            with open(CRASH_LOG, "wb") as f:
                f.write(tail)
    except OSError:
        pass
    try:
        _crash_file = open(CRASH_LOG, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    stamp = lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    _crash_file.write(f"\n=== {stamp()}  inicio (pid {os.getpid()}) ===\n")
    faulthandler.enable(_crash_file, all_threads=True)

    def excepthook(kind, value, tb):
        _crash_file.write(f"[{stamp()}] Excepción no controlada:\n")
        _crash_file.write("".join(traceback.format_exception(kind, value, tb)))
    sys.excepthook = excepthook

    levels = {QtMsgType.QtCriticalMsg: "CRITICAL", QtMsgType.QtFatalMsg: "FATAL"}

    def qt_messages(kind, context, message):
        # solo lo grave: los avisos de Qt son muchos y casi nunca explican un cierre
        if kind in levels:
            _crash_file.write(f"[{stamp()}] Qt {levels[kind]}: {message}\n")
            _crash_file.flush()
    qInstallMessageHandler(qt_messages)
    _install_native_crash_filter(stamp)


_native_filter = None  # referencias vivas: si el GC se lleva el callback, Windows saltaría a basura


def _install_native_crash_filter(stamp):
    """faulthandler ignora a propósito las excepciones C++ (como std::bad_alloc, el crash del 11/11):
    este filtro de último recurso de Windows las anota (código, tipo y mensaje) junto con la pila de
    Python, y luego deja seguir el cierre normal (informe de Windows y volcado)."""
    global _native_filter
    import faulthandler
    from ctypes import POINTER, WINFUNCTYPE, c_long, c_uint32, c_uint64, c_void_p, cast, string_at
    kernel32 = ctypes.windll.kernel32
    kernel32.SetUnhandledExceptionFilter.restype = c_void_p
    kernel32.SetUnhandledExceptionFilter.argtypes = [c_void_p]
    FILTER = WINFUNCTYPE(c_long, c_void_p)
    previous = []

    def cpp_details(rec):
        """Tipo y what() de una excepción C++ de MSVC (código 0xE06D7363), leídos de su ThrowInfo."""
        if c_uint32.from_address(rec + 24).value < 4:  # NumberParameters
            return ""
        obj, throw_info, base = (c_uint64.from_address(rec + 32 + 8 * i).value for i in (1, 2, 3))
        u32 = lambda a: c_uint32.from_address(a).value  # noqa: E731
        catchable_types = base + u32(throw_info + 12)
        type_desc = base + u32(base + u32(catchable_types + 4) + 4)
        name = string_at(type_desc + 16).decode("ascii", "replace")
        what = string_at(c_uint64.from_address(obj + 8).value).decode("utf-8", "replace") if obj else ""
        return f" tipo {name}" + (f": {what}" if what else "")

    @FILTER
    def on_crash(info):
        try:
            rec = cast(info, POINTER(c_void_p))[0]  # EXCEPTION_POINTERS.ExceptionRecord
            code = c_uint32.from_address(rec).value
            extra = ""
            if code == 0xE06D7363:
                try:
                    extra = " (excepción C++" + cpp_details(rec) + ")"
                except Exception:  # noqa: BLE001
                    extra = " (excepción C++)"
            _crash_file.write(f"[{stamp()}] Cierre por excepción nativa 0x{code:08X}{extra}\n")
            faulthandler.dump_traceback(_crash_file, all_threads=True)
            _crash_file.flush()
        except Exception:  # noqa: BLE001
            pass
        return previous[0](info) if previous else 0  # 0 = EXCEPTION_CONTINUE_SEARCH

    old = kernel32.SetUnhandledExceptionFilter(cast(on_crash, c_void_p))
    if old:
        previous.append(FILTER(old))
    _native_filter = (on_crash, previous)


def clean_temp_conversions():
    """Borra temporales de conversiones que quedaron a medias (se cerró la app mientras optimizaba)."""
    try:
        for name in os.listdir(LIBRARY):
            if ".tmp." in name and name.endswith(".mp4"):
                try:
                    os.remove(os.path.join(LIBRARY, name))
                except OSError:
                    pass
    except OSError:
        pass


def main():
    # Sin esto Windows agrupa la ventana bajo python(w).exe y muestra su icono en la barra de tareas
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    enable_crash_log()
    app = QApplication(sys.argv)
    if "--selftest" in sys.argv:
        args = sys.argv[sys.argv.index("--selftest") + 1:]
        sys.exit(selftest(args[0], args[1] if len(args) > 1 else None))
    if "--smoketest" in sys.argv:  # prueba completa antes de publicar (ver smoketest.py / release.bat)
        import smoketest
        app.setStyleSheet(STYLE)
        os._exit(smoketest.run(sys.modules[__name__], sys.argv[sys.argv.index("--smoketest") + 1]))
    app.setWindowIcon(QIcon(ICON_PATH))
    if "--desinstalar" in sys.argv:  # desde «Aplicaciones instaladas» de Windows
        INSTALACION.desinstalar(f"Los videos de tu biblioteca ({LIBRARY}) no se borran.")
        os._exit(0)
    if INSTALACION.ofrecer(f"Los videos de tu biblioteca ({LIBRARY}) no se borran."):
        # .exe portable: instalar / actualizar / reinstalar / desinstalar, o confirma que ya está al día
        os._exit(0)
    if already_running():
        return
    refresh_autostart()
    clean_temp_conversions()  # solo con esta instancia ya confirmada como la única
    app.setApplicationName(DISPLAY_NAME)
    app.setWindowIcon(QIcon(ICON_PATH))
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    settings = load_settings()
    current = settings.get("current")
    if current and not os.path.exists(current):
        # La carpeta se movió o se copió a otro PC: buscar el mismo video en esta biblioteca
        moved = os.path.join(LIBRARY, os.path.basename(current))
        if os.path.exists(moved):
            settings["current"] = moved
        else:
            settings.pop("current", None)
        save_settings(settings)
    if settings.get("rotation") == -1:  # "Rotar al iniciar": elegir otro video en cada arranque
        choice = library.pick_next(library.videos(LIBRARY), settings.get("favorites", []), settings.get("current"))
        if choice:
            settings["current"] = choice
            save_settings(settings)
    wallpaper = DesktopWallpaper(os.path.join(THUMBS, "glitches.json"))
    wallpaper.all_screens = settings.get("all_screens", False)
    wallpaper.pause_when_covered = settings.get("pause_when_covered", True)
    win = MainWindow(wallpaper, settings)

    server = QLocalServer()
    QLocalServer.removeServer(APP_NAME)
    server.listen(APP_NAME)
    def on_connection():
        sock = server.nextPendingConnection()
        # Solo se muestra si la otra copia lo pide (el usuario la abrió); se espera un poco al mensaje
        if sock.bytesAvailable() or sock.waitForReadyRead(300):
            if sock.readAll().data().startswith(b"show"):
                win.show_window()
    server.newConnection.connect(on_connection)
    current = settings.get("current")
    if current and os.path.exists(current):
        wallpaper.set_video(current)
        win._update_now_playing()
        win.ensure_profile(current)
    if "--minimized" not in sys.argv:
        win.show()
    QTimer.singleShot(1500, INSTALACION.avisar_novedades)  # «se instaló / se actualizó: esto es lo nuevo» (una vez)
    code = app.exec()
    # Todo se guarda en el momento (ajustes, biblioteca) y el fondo ya se detuvo en _quit. Salir ya,
    # sin esperar a peticiones de red lentas que mantendrían el proceso vivo (e invisible) un buen rato.
    os._exit(code)


if __name__ == "__main__":
    main()
