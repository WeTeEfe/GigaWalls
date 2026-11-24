"""Reproduce un video en bucle detras de los iconos del escritorio (truco WorkerW)."""
import ctypes
import threading
from ctypes import wintypes

import cv2
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QLabel

import glitches

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindow.argtypes = [wintypes.HWND]

shell32 = ctypes.windll.shell32
dwmapi = ctypes.windll.dwmapi
user32.MonitorFromWindow.restype = ctypes.c_void_p
user32.MonitorFromPoint.restype = ctypes.c_void_p
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]

SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

# QUNS_BUSY (pantalla completa), QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE
FULLSCREEN_STATES = {2, 3, 4}

# comandos de la barra de tareas: «Minimizar todo» y deshacerlo (lo mismo que Win+M / Win+Shift+M)
_MINIMIZAR_TODO, _DESHACER_MINIMIZAR = 419, 416


def _barra_tareas(comando):
    barra = user32.FindWindowW("Shell_TrayWnd", None)
    if barra:
        user32.PostMessageW(barra, 0x0111, comando, 0)  # WM_COMMAND


def minimizar_ventanas():
    """Minimiza todas las ventanas para que se vea el escritorio con el fondo nuevo."""
    _barra_tareas(_MINIMIZAR_TODO)


def restaurar_ventanas():
    """Devuelve las ventanas que minimizó minimizar_ventanas()."""
    _barra_tareas(_DESHACER_MINIMIZAR)


def _find_workerw():
    """Devuelve el HWND del WorkerW que queda detras de los iconos, o None si el escritorio del
    Explorador todavia no existe (inicio de sesion, o el Explorador se esta reiniciando)."""
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return None
    result = wintypes.DWORD()
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(result))

    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum(hwnd, _):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            # el WorkerW hermano siguiente es el que hay que usar
            found.append(user32.FindWindowExW(None, hwnd, "WorkerW", None))
        return True

    user32.EnumWindows(enum, 0)
    if not found:  # aun no hay capa de iconos: el escritorio esta a medio crear
        return None
    workerw = next((h for h in found if h), None)
    # Windows 11 24H2+: el WorkerW queda dentro de Progman
    return workerw or user32.FindWindowExW(progman, None, "WorkerW", None) or progman


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetLayeredWindowAttributes.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
                                              ctypes.POINTER(ctypes.c_ubyte),
                                              ctypes.POINTER(wintypes.DWORD)]

# WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE: overlays y ventanas auxiliares que no tapan
_IGNORED_EXSTYLE = 0x20 | 0x80 | 0x08000000
_WS_EX_LAYERED = 0x80000


def _frame_rect(hwnd):
    """Rectangulo visible de la ventana (sin el borde invisible que Windows anade al maximizar)."""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:  # EXTENDED_FRAME_BOUNDS
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def _invisible_layered(hwnd, exstyle):
    """Ventana en capas totalmente transparente (overlays de juegos, grabadores, etc.)."""
    if not exstyle & _WS_EX_LAYERED:
        return False
    alpha, flags = ctypes.c_ubyte(), wintypes.DWORD()
    if not user32.GetLayeredWindowAttributes(hwnd, None, ctypes.byref(alpha), ctypes.byref(flags)):
        return False
    return bool(flags.value & 0x2) and alpha.value < 10  # LWA_ALPHA casi 0


def _covered_monitors():
    """Monitores que de verdad quedan tapados por una ventana maximizada o a pantalla completa.

    No basta con IsZoomed: muchas apps (Spotify, overlays de NVIDIA/Steam/Discord, ventanas
    auxiliares) se declaran maximizadas sin cubrir la pantalla o siendo invisibles, y con eso el
    fondo quedaba en pausa para siempre. Se exige que la ventana cubra casi toda el area de trabajo."""
    covered = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if _class_name(hwnd) in SHELL_CLASSES:
            return True
        exstyle = user32.GetWindowLongW(hwnd, -20) & 0xFFFFFFFF
        if exstyle & _IGNORED_EXSTYLE or _invisible_layered(hwnd, exstyle):
            return True
        cloaked = ctypes.c_int()  # ventanas de apps UWP ocultas o de otro escritorio virtual
        dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return True
        monitor = user32.MonitorFromWindow(hwnd, 2)
        info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return True
        r, work = _frame_rect(hwnd), info.rcWork
        ix = max(0, min(r.right, work.right) - max(r.left, work.left))
        iy = max(0, min(r.bottom, work.bottom) - max(r.top, work.top))
        area = (work.right - work.left) * (work.bottom - work.top)
        if area > 0 and ix * iy >= 0.9 * area:
            covered.add(monitor)
        return True

    user32.EnumWindows(enum, 0)
    return covered


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _embed(widget, screen, workerw):
    """Coloca el widget detras de los iconos, cubriendo exactamente `screen`."""
    virtual = QApplication.primaryScreen().virtualGeometry()
    geo = screen.geometry()
    widget.setWindowFlags(Qt.FramelessWindowHint)
    widget.hwnd = int(widget.winId())  # fuerza la creacion del HWND; se guarda para saber si sigue vivo
    user32.SetParent(widget.hwnd, workerw)
    widget.setGeometry(geo.x() - virtual.x(), geo.y() - virtual.y(), geo.width(), geo.height())
    widget.show()


class _ScreenWallpaper(QVideoWidget):
    def __init__(self, screen, workerw):
        super().__init__()
        self.target_screen = screen  # screen() no sirve: tras incrustarla en WorkerW da siempre la principal
        self.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)
        _embed(self, screen, workerw)


class _StillWallpaper(QLabel):
    """Fotograma fijo del video para pantallas donde no merece la pena reproducirlo."""

    def __init__(self, screen, workerw, frame):
        super().__init__()
        size = screen.geometry().size() * screen.devicePixelRatio()
        pm = QPixmap.fromImage(frame).scaled(size, Qt.KeepAspectRatioByExpanding,
                                             Qt.SmoothTransformation)
        x, y = (pm.width() - size.width()) // 2, (pm.height() - size.height()) // 2
        self.setPixmap(pm.copy(x, y, size.width(), size.height()))
        _embed(self, screen, workerw)


def _first_frame(path):
    """Fotograma representativo (~1 s) del video como QImage, o None."""
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, _ = rgb.shape
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class DesktopWallpaper:
    def __init__(self, glitch_cache=None):
        self._glitch_cache = glitches.Cache(glitch_cache) if glitch_cache else None
        self._skip = []  # tramos (inicio_us, fin_us) del video actual que no se muestran (ver glitches.py)
        self.all_screens = False  # False: video en la principal, imagen fija en las demas
        self.pause_when_covered = True
        self._videos = []  # pantallas que reproducen video
        self._stills = []  # pantallas con imagen fija
        self._player = None
        self._path = None
        self._workerw = None  # None con _path puesto: fondo pendiente, el escritorio aun no esta listo
        self._sink = None  # recibe los fotogramas del reproductor; de aqui se reparten a las pantallas
        self._visible = []  # pantallas de video a las que se les reparten fotogramas (las que se ven)
        self._paused_by_user = False
        self._auto_paused = False
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._check_fullscreen)
        # Win+P o enchufar/apagar un monitor: se espera a que Windows termine de reacomodar y se recoloca el fondo
        self._relayout = QTimer()
        self._relayout.setSingleShot(True)
        self._relayout.setInterval(1500)
        self._relayout.timeout.connect(self._on_screens_changed)
        self._hooked = False

    def _hook_screens(self):
        if self._hooked:
            return
        self._hooked = True
        app = QApplication.instance()
        for signal in (app.screenAdded, app.screenRemoved, app.primaryScreenChanged):
            signal.connect(lambda *_: self._relayout.start())

    def _on_screens_changed(self):
        if self._path:
            self.set_video(self._path)

    def _make_player(self):
        player = QMediaPlayer()
        audio = QAudioOutput()
        audio.setMuted(True)
        player.setAudioOutput(audio)
        player.setLoops(QMediaPlayer.Loops.Infinite)
        player._audio = audio  # evita que el GC lo destruya
        return player

    def set_video(self, path):
        self.stop()
        self._hook_screens()
        self._path = path
        workerw = self._workerw = _find_workerw()
        if not workerw:
            # Sin escritorio (el Explorador aun no arranco o se esta reiniciando) no hay donde incrustar
            # el video: se deja pendiente y _check_fullscreen lo reintenta cada 2 s.
            self._timer.start()
            return
        primary_screen = QApplication.primaryScreen()
        screens = QApplication.screens()
        screens.sort(key=lambda s: s is not primary_screen)  # la principal primero
        still = None if self.all_screens else _first_frame(path)
        for screen in screens:
            if self.all_screens or screen is primary_screen or still is None:
                self._videos.append(_ScreenWallpaper(screen, workerw))
            else:
                self._stills.append(_StillWallpaper(screen, workerw, still))
        # Un solo reproductor: se decodifica una vez hacia un sumidero propio y los fotogramas se
        # reparten solo a las pantallas que se ven (ver _route). Una pantalla tapada conserva su
        # ultimo fotograma y no gasta GPU en dibujar.
        self._player = self._make_player()
        self._sink = QVideoSink()
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._load_glitches(path)
        self._player.setVideoOutput(self._sink)
        self._route(self._videos)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self._paused_by_user = False
        self._timer.start()

    def stop(self):
        self._timer.stop()
        # Orden de cierre: cortar el reenvio de fotogramas, parar el reproductor y soltar la salida
        # de video ANTES de destruir los widgets; el reproductor se libera despues (deleteLater),
        # no en medio de una decodificacion.
        self._route([])
        if self._player:
            player, self._player = self._player, None
            player.stop()
            player.setVideoOutput(None)
            player.setSource(QUrl())
            player.deleteLater()
            player._audio.deleteLater()
        if self._sink:
            try:
                self._sink.videoFrameChanged.disconnect(self._on_frame)
            except (RuntimeError, TypeError):
                pass
            self._sink.deleteLater()
            self._sink = None
        for w in self._videos + self._stills:
            w.hide()
            w.deleteLater()
        self._videos.clear()
        self._stills.clear()
        self._path = None
        self._workerw = None

    @property
    def active(self):
        return bool(self._videos)

    @property
    def paused(self):
        return self._paused_by_user

    def toggle_pause(self):
        self._paused_by_user = not self._paused_by_user
        self._apply_state()

    def _apply_state(self):
        pause = self._paused_by_user or self._auto_paused
        if self._player:
            self._player.pause() if pause else self._player.play()

    @staticmethod
    def _monitor_of(w):
        """Monitor de Windows (HMONITOR) donde esta la pantalla de video `w`."""
        # Por su propio HWND: calcularlo desde la geometria de Qt falla con monitores de distinto
        # escalado (Qt no escala la esquina de cada pantalla).
        monitor = user32.MonitorFromWindow(w.hwnd, 2) if user32.IsWindow(w.hwnd) else None
        if monitor:
            return monitor
        g = w.target_screen.geometry()
        r = w.target_screen.devicePixelRatio()
        pt = wintypes.POINT(int((g.x() + g.width() / 2) * r), int((g.y() + g.height() / 2) * r))
        return user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST

    def _route(self, visible):
        """Envia fotogramas solo a las pantallas de `visible`; las demas conservan el ultimo."""
        self._visible = list(visible)

    def _load_glitches(self, path):
        """Busca los fotogramas defectuosos del video (en segundo plano la primera vez)."""
        self._skip = []
        cache = self._glitch_cache
        if not cache:
            return
        spans = cache.get(path)
        if spans is not None:
            self._skip = spans
            return

        def job():
            try:
                found = glitches.analyze(path)
            except Exception:  # noqa: BLE001 - sin analisis se reproduce tal cual
                return
            cache.put(path, found)
            if self._path == path:
                self._skip = found
        threading.Thread(target=job, daemon=True).start()

    def _on_frame(self, frame):
        # Fotogramas que no se pasan a la pantalla (esta conserva el ultimo bueno): los vacios que
        # puede mandar el reproductor al dar la vuelta y los defectuosos del propio archivo, que en
        # bucle se ven como un destello en cada vuelta.
        if not frame.isValid():
            return
        t = frame.startTime()
        if t >= 0:
            for t0, t1 in self._skip:
                if t0 - 3000 <= t < t1 - 3000:
                    return
        for w in self._visible:
            w.videoSink().setVideoFrame(frame)

    def _desktop_alive(self):
        """False si el Explorador se reinicio: al morir destruye su escritorio y, con el, nuestras
        ventanas incrustadas."""
        return bool(self._workerw and user32.IsWindow(self._workerw)
                    and all(user32.IsWindow(w.hwnd) for w in self._videos + self._stills))

    def _rebuild(self):
        """Vuelve a poner el fondo tras perder el escritorio (o cuando por fin aparece). Seguir
        reproduciendo sobre ventanas destruidas congela la interfaz 2 s por fotograma."""
        path, paused = self._path, self._paused_by_user
        self.set_video(path)  # si el escritorio nuevo aun no esta listo, queda pendiente otra vez
        self._paused_by_user = paused
        self._auto_paused = False
        self._apply_state()

    def _check_fullscreen(self):
        """Deja de dibujar donde no se ve: en cada pantalla tapada por una ventana maximizada se corta
        el video (las demas siguen), y si estan todas tapadas o hay una app a pantalla completa se
        pausa el reproductor. Tambien repone el fondo si el Explorador se reinicio."""
        if self._path and not self._desktop_alive():
            self._rebuild()
            return
        if not self._videos:
            return
        state = ctypes.c_int()
        shell32.SHQueryUserNotificationState(ctypes.byref(state))
        full = state.value in FULLSCREEN_STATES
        visible = self._videos
        if not full and self.pause_when_covered:
            covered = _covered_monitors()
            try:
                visible = [w for w in self._videos if self._monitor_of(w) not in covered]
            except RuntimeError:
                # Se apago o desconecto un monitor (o la PC volvio de suspension): Qt ya destruyo su
                # QScreen pero _relayout aun no rehizo las pantallas (espera 1,5 s). Se espera a eso.
                self._relayout.start()
                return
            full = not visible
        if not full:
            self._route(visible)
        if full != self._auto_paused:
            self._auto_paused = full
            self._apply_state()
