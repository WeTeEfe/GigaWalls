"""Progreso visible de descargas y conversiones.

  Tarea              una operación (descargar, reflejar, optimizar, importar) con sus etapas y su avance.
  PanelTareas        tarjetas apiladas abajo a la derecha de la ventana: la que corre, las de la cola y las
                     que terminaron (verde) o fallaron (rojo), con sus botones.
  DelegadoProgreso   oscurece la miniatura que se está bajando y dibuja un aro con el % encima; a lo que ya
                     está en la biblioteca le pone «✔ En tu biblioteca».
  AvisoAplicado      aviso propio (no el globo gris de Windows) cuando el fondo queda en el escritorio.
  BarraTareasWindows el botón de la app en la barra de tareas se llena en verde (ITaskbarList3).
"""
import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget)

from theme import rounded

ACENTO = "#7c5cff"
VERDE = "#7ac70c"   # el verde del logo («Walls»)
ROJO = "#ff6b85"
GRIS = "#a2a9c2"


def _duracion(segundos):
    segundos = max(1, int(round(segundos)))
    if segundos < 60:
        return f"{segundos} s"
    m, s = divmod(segundos, 60)
    return f"{m} min {s:02d} s" if m < 10 else f"{m} min"


def portada(pixmap, ancho, alto, radio=8):
    """La imagen recortada para llenar ancho×alto (como una portada) y con esquinas redondeadas."""
    if pixmap is None or pixmap.isNull():
        return None
    p = pixmap.scaled(ancho, alto, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    p = p.copy((p.width() - ancho) // 2, (p.height() - alto) // 2, ancho, alto)
    return rounded(p, radio)


# ---------------------------------------------------------------- tarea
class Tarea(QObject):
    """Estado de una operación. La interfaz escucha `cambio`; el trabajo llama a etapa/avance/terminar."""
    cambio = Signal()
    COLA, ACTIVA, LISTA, ERROR, CANCELADA = range(5)

    def __init__(self, titulo, etapas, clave=None, miniatura=None):
        super().__init__()
        self.titulo = titulo
        self.etapas = list(etapas)      # nombres cortos: «Descargar», «Optimizar», «Aplicar»
        self.clave = clave              # url del catálogo o ruta de la biblioteca (para la miniatura)
        self.miniatura = miniatura
        self.estado = self.COLA
        self.indice = 0                 # etapa en curso
        self.fraccion = None            # 0..1 o None mientras no se sabe cuánto falta
        self.detalle = "En cola"
        self.resultado = ""             # texto final («Aplicado en tu escritorio»)
        self.acciones = []              # [(texto, función, principal)] al terminar
        self.posicion = 0               # lugar en la cola (1 = la siguiente)
        self.cancelable = True
        self.cancelada = False          # lo miran las descargas para cortar
        self.al_cancelar = None
        self._base = ""
        self._t0 = 0.0
        self._ultimo = 0.0

    @property
    def en_curso(self):
        return self.estado in (self.COLA, self.ACTIVA)

    @property
    def nombre_etapa(self):
        return self.etapas[min(self.indice, len(self.etapas) - 1)]

    def etapa(self, indice, detalle, cancelable=False):
        self.estado, self.indice, self.fraccion = self.ACTIVA, indice, None
        self.detalle = self._base = detalle
        self.cancelable = cancelable
        self._t0 = time.monotonic()
        self.cambio.emit()

    def avance(self, hecho, total, bytes_=False):
        if not total or self.estado != self.ACTIVA:
            return
        self.fraccion = max(0.0, min(1.0, hecho / total))
        ahora = time.monotonic()
        if ahora - self._ultimo < 0.12 and self.fraccion < 1:  # ffmpeg y las descargas avisan muy seguido
            return
        self._ultimo = ahora
        partes = [self._base]
        if bytes_:
            partes.append(f"{hecho / 1e6:.1f} de {total / 1e6:.1f} MB")
        transcurrido = ahora - self._t0
        if transcurrido > 1.5 and 0.03 < self.fraccion < 1:
            partes.append(f"quedan {_duracion(transcurrido / self.fraccion * (1 - self.fraccion))}")
        self.detalle = "  ·  ".join(partes)
        self.cambio.emit()

    def terminar(self, resultado, detalle="", acciones=()):
        self.estado, self.indice, self.fraccion = self.LISTA, len(self.etapas), 1.0
        self.resultado, self.detalle, self.acciones = resultado, detalle, list(acciones)
        self.cambio.emit()

    def fallar(self, detalle):
        self.estado, self.detalle = self.ERROR, detalle
        self.cambio.emit()

    def cancelar(self):
        """Lo pide el usuario (✕ de la tarjeta). En la cola se descarta ya; en curso, la descarga corta sola."""
        if not self.en_curso or not self.cancelable:
            return
        self.cancelada = True
        if self.estado == self.COLA:
            self.marcar_cancelada()
        else:
            self.detalle = "Cancelando…"
            self.cambio.emit()
        if self.al_cancelar:
            self.al_cancelar(self)

    def marcar_cancelada(self):
        self.estado, self.detalle = self.CANCELADA, "Cancelada"
        self.cambio.emit()


# ---------------------------------------------------------------- barra de progreso
class BarraProgreso(QWidget):
    """Barra gruesa con el color del estado. Sin fracción conocida, un tramo que va y viene."""

    def __init__(self, alto=8):
        super().__init__()
        self.setFixedHeight(alto)
        self.fraccion, self.color = None, QColor(ACENTO)
        self._fase = 0.0
        self._reloj = QTimer(self, interval=30)
        self._reloj.timeout.connect(self._paso)

    def poner(self, fraccion, color):
        self.fraccion, self.color = fraccion, QColor(color)
        if fraccion is None and self.isVisible():
            self._reloj.start()
        else:
            self._reloj.stop()
        self.update()

    def _paso(self):
        self._fase = (self._fase + 0.018) % 1.0
        self.update()

    def showEvent(self, e):
        if self.fraccion is None:
            self._reloj.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._reloj.stop()
        super().hideEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        radio = r.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#363d58"))
        p.drawRoundedRect(r, radio, radio)
        p.setBrush(self.color)
        if self.fraccion is None:
            ancho = r.width() * 0.28
            x = -ancho + (r.width() + ancho) * self._fase
            p.setClipRect(r)
            p.drawRoundedRect(QRectF(x, 0, ancho, r.height()), radio, radio)
        elif self.fraccion > 0:
            p.drawRoundedRect(QRectF(0, 0, max(r.height(), r.width() * self.fraccion), r.height()), radio, radio)
        p.end()


# ---------------------------------------------------------------- tarjeta
_ESTILO_TARJETA = f"""
QFrame#tarjeta {{ background: #252a40; border: 1px solid #3d4563; border-radius: 14px; }}
QFrame#tarjeta[estado="lista"] {{ border-color: #5c8f1f; background: #1f2a1c; }}
QFrame#tarjeta[estado="error"] {{ border-color: #8a3550; background: #2d1c26; }}
QFrame#tarjeta QLabel {{ background: transparent; }}
QLabel#tt_titulo {{ font-size: 13px; font-weight: 700; color: #ffffff; }}
QLabel#tt_detalle {{ font-size: 12px; color: {GRIS}; }}
QLabel#tt_pct {{ font-size: 13px; font-weight: 700; color: #ffffff; }}
QLabel#tt_resultado {{ font-size: 13px; font-weight: 700; color: {VERDE}; }}
QLabel#tt_mini {{ background: #12151f; border-radius: 8px; color: #4b5170; font-size: 22px; }}
QPushButton#tt_cerrar {{ background: transparent; border: none; color: #6b7189; font-size: 14px;
                         padding: 0; min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
                         border-radius: 11px; }}
QPushButton#tt_cerrar:hover {{ background: #2c3249; color: #ffffff; }}
QFrame#tarjeta QPushButton#tt_accion {{ padding: 3px 12px; font-size: 12px; border-radius: 9px; }}
QFrame#tarjeta QPushButton#tt_principal {{ padding: 3px 12px; font-size: 12px; border-radius: 9px;
                                          background: {ACENTO}; border: none; color: white; font-weight: 600; }}
QFrame#tarjeta QPushButton#tt_principal:hover {{ background: #8f73ff; }}
QLabel#tt_mas {{ background: #252a40; border: 1px solid #3d4563; border-radius: 12px; color: #b4bad0;
                 font-size: 12px; padding: 5px 12px; }}
"""


class TarjetaTarea(QFrame):
    """Tarjeta horizontal y baja: miniatura | título, etapas, barra con % y detalle (o botones al terminar)."""
    MINI = (112, 63)
    ANCHO, ALTO = 410, 96

    def __init__(self, tarea, al_cerrar):
        super().__init__(objectName="tarjeta")
        self.tarea = tarea
        self._al_cerrar = al_cerrar
        self.setFixedSize(self.ANCHO, self.ALTO)
        self.setStyleSheet(_ESTILO_TARJETA)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(10, 10, 10, 10)
        raiz.setSpacing(12)
        self.mini = QLabel("🎞", objectName="tt_mini")
        self.mini.setFixedSize(*self.MINI)
        self.mini.setAlignment(Qt.AlignCenter)
        pm = portada(tarea.miniatura, *self.MINI)
        if pm:
            self.mini.setPixmap(pm)
        raiz.addWidget(self.mini, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(4)
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.titulo = QLabel(objectName="tt_titulo")
        self.titulo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        fila.addWidget(self.titulo, 1)
        self.cerrar = QPushButton("✕", objectName="tt_cerrar")
        self.cerrar.setCursor(Qt.PointingHandCursor)
        self.cerrar.clicked.connect(self._cerrar)
        fila.addWidget(self.cerrar, 0, Qt.AlignTop)
        col.addLayout(fila)
        self.pasos = QLabel()
        self.pasos.setTextFormat(Qt.RichText)
        col.addWidget(self.pasos)
        self.resultado = QLabel(objectName="tt_resultado")  # en lugar de las etapas al terminar
        col.addWidget(self.resultado)
        barra = QHBoxLayout()
        barra.setSpacing(8)
        self.barra = BarraProgreso(7)
        barra.addWidget(self.barra, 1)
        self.pct = QLabel(objectName="tt_pct")
        self.pct.setFixedWidth(40)
        self.pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        barra.addWidget(self.pct)
        col.addLayout(barra)
        self.abajo = QHBoxLayout()
        self.abajo.setSpacing(6)
        # una sola línea recortada (texto que se parte deja la tarjeta sin alto fijo)
        self.detalle = QLabel(objectName="tt_detalle")
        self.detalle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.abajo.addWidget(self.detalle, 1)
        col.addLayout(self.abajo)
        raiz.addLayout(col, 1)
        self._con_botones = False

        self._quitar = QTimer(self, singleShot=True)
        self._quitar.timeout.connect(self._quitar_si_se_vio)
        tarea.cambio.connect(self.refrescar)
        self.refrescar()

    def _texto_titulo(self):
        ancho = self.titulo.width() if self.titulo.width() > 50 else 230
        return self.titulo.fontMetrics().elidedText(self.tarea.titulo, Qt.ElideRight, ancho)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.titulo.setText(self._texto_titulo())

    def _pasos_html(self):
        t, partes = self.tarea, []
        for i, nombre in enumerate(t.etapas):
            if t.estado == t.LISTA or i < t.indice:
                partes.append(f'<span style="color:{VERDE}">✔ {nombre}</span>')
            elif i == t.indice and t.estado == t.ERROR:
                partes.append(f'<span style="color:{ROJO}; font-weight:700">✕ {nombre}</span>')
            elif i == t.indice and t.estado == t.ACTIVA:
                partes.append(f'<span style="color:#b9a8ff; font-weight:700">● {nombre}</span>')
            else:
                partes.append(f'<span style="color:#8189a4">○ {nombre}</span>')
        return '<span style="font-size:12px">' + ' <span style="color:#4b5170">›</span> '.join(partes) + "</span>"

    def refrescar(self):
        t = self.tarea
        self.titulo.setText(self._texto_titulo())
        self.pasos.setText(self._pasos_html())
        estado = {t.LISTA: "lista", t.ERROR: "error"}.get(t.estado, "")
        if self.property("estado") != estado:
            self.setProperty("estado", estado)
            self.style().unpolish(self)
            self.style().polish(self)
        self.resultado.setVisible(t.estado == t.LISTA)
        self.pasos.setVisible(t.estado != t.LISTA)
        # terminada: el «✔ Aplicado…» ya lo dice todo; la barra deja su lugar a los botones
        self.barra.setVisible(t.estado != t.LISTA)
        self.pct.setVisible(t.estado != t.LISTA)
        self.resultado.setText(f"✔  {t.resultado}")
        if t.estado == t.COLA:
            self.barra.poner(0, "#3a4160")
            self.pct.setText("")
            self.detalle.setText(f"En cola · empieza cuando termine la anterior" + (f" (#{t.posicion})" if t.posicion > 1 else ""))
        elif t.estado == t.ACTIVA:
            self.barra.poner(t.fraccion, ACENTO)
            self.pct.setText(f"{int(t.fraccion * 100)} %" if t.fraccion is not None else "")
            self.detalle.setText(t.detalle)
        elif t.estado == t.LISTA:
            self.barra.poner(1.0, VERDE)
            self.pct.setText("100 %")
            self.detalle.setText(t.detalle)
        elif t.estado == t.ERROR:
            self.barra.poner(t.fraccion or 0, ROJO)
            self.pct.setText("")
            self.detalle.setText(t.detalle)
        else:
            self.barra.poner(0, "#3a4160")
            self.pct.setText("")
            self.detalle.setText("Cancelada")
        self.detalle.setStyleSheet(f"color: {ROJO};" if t.estado == t.ERROR else "")
        completo = self.detalle.text()
        self.detalle.setToolTip(completo if len(completo) > 60 else "")
        ancho = 250 - (sum(b.sizeHint().width() + 6 for b in self.findChildren(QPushButton)
                           if b is not self.cerrar) if self._con_botones else 0)
        self.detalle.setText(self.detalle.fontMetrics().elidedText(completo, Qt.ElideRight, max(40, ancho)))
        self.detalle.setVisible(bool(completo))
        self.cerrar.setToolTip("Cancelar" if t.en_curso else "Cerrar")
        self.cerrar.setVisible(not t.en_curso or t.cancelable)
        if t.estado == t.LISTA and t.acciones and not self._con_botones:
            self._con_botones = True
            for texto, fn, principal in t.acciones:
                b = QPushButton(texto, objectName="tt_principal" if principal else "tt_accion")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, fn=fn: (fn(), self._al_cerrar(self.tarea)))
                b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                self.abajo.addWidget(b, 0, Qt.AlignRight | Qt.AlignVCenter)
            self.refrescar()
        if t.estado in (t.LISTA, t.CANCELADA) and not self._quitar.isActive():
            self._quitar.start(1500 if t.estado == t.CANCELADA else 12000)

    def _quitar_si_se_vio(self):
        """Las terminadas se van solas, pero solo después de que se hayan podido ver."""
        if self.tarea.estado == Tarea.LISTA and (self.underMouse() or not self.window().isActiveWindow()):
            self._quitar.start(4000)
            return
        self._al_cerrar(self.tarea)

    def _cerrar(self):
        if self.tarea.en_curso:
            self.tarea.cancelar()
        else:
            self._al_cerrar(self.tarea)


class PanelTareas(QFrame):
    """Franja fija debajo del contenido (no flota encima de nada): las tarjetas una al lado de la otra,
    en el orden de la cola. Caben las que entren a lo ancho; el resto se resume en «+N más en cola».
    Solo se ve mientras hay algo en curso o recién terminado."""

    def __init__(self):
        super().__init__(objectName="franja")
        self.setStyleSheet(_ESTILO_TARJETA + """
            QFrame#franja { background: transparent; border: none; border-top: 1px solid #353c5a; }""")
        self._tarjetas = {}
        self._orden = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 10, 24, 6)
        lay.setSpacing(10)
        self._lay = lay
        self._mas = QLabel(objectName="tt_mas")
        lay.addWidget(self._mas, 0, Qt.AlignVCenter)
        lay.addStretch()
        self._mas.hide()
        self.setFixedHeight(TarjetaTarea.ALTO + 16)
        self.hide()

    def agregar(self, tarea):
        tarjeta = TarjetaTarea(tarea, self.quitar)
        self._tarjetas[tarea] = tarjeta
        self._orden.append(tarea)
        self._lay.insertWidget(len(self._orden) - 1, tarjeta)
        self._acomodar()

    def quitar(self, tarea):
        tarjeta = self._tarjetas.pop(tarea, None)
        if tarjeta is None:
            return
        self._orden.remove(tarea)
        tarjeta.hide()
        tarjeta.deleteLater()
        self._acomodar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._acomodar()

    def _acomodar(self):
        margen = self._lay.contentsMargins()
        libre = self.width() - margen.left() - margen.right() - 130  # lugar para «+N más en cola»
        caben = max(1, libre // (TarjetaTarea.ANCHO + self._lay.spacing()))
        visibles = self._orden[:caben]
        for t in self._orden:
            self._tarjetas[t].setVisible(t in visibles)
        resto = len(self._orden) - len(visibles)
        self._mas.setText(f"+{resto} más")
        self._mas.setToolTip(chr(10).join(t.titulo for t in self._orden[caben:]))
        self._mas.setVisible(resto > 0)
        self.setVisible(bool(self._orden))


# ---------------------------------------------------------------- miniaturas de la cuadrícula
class DelegadoProgreso(QStyledItemDelegate):
    """Pinta la tarjeta normal y encima, si toca: el aro de progreso o «✔ En tu biblioteca».
    tarea_de(datos) -> Tarea o None; en_biblioteca(datos) -> bool (datos = Qt.UserRole del ítem)."""

    def __init__(self, vista, tarea_de, en_biblioteca):
        super().__init__(vista)
        self._tarea_de, self._en_biblioteca = tarea_de, en_biblioteca

    def paint(self, p, option, index):
        super().paint(p, option, index)
        datos = index.data(Qt.UserRole)
        if datos is None:
            return
        tarea = self._tarea_de(datos)
        listo = tarea is None and self._en_biblioteca(datos)
        if not tarea and not listo:
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        estilo = opt.widget.style() if opt.widget else QApplication.style()
        r = estilo.subElementRect(QStyle.SE_ItemViewItemDecoration, opt, opt.widget)
        if r.width() < 40:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if tarea:
            self._pintar_tarea(p, QRectF(r), tarea)
        else:
            self._pastilla(p, QRectF(r), "✔  En tu biblioteca", QColor(VERDE), QColor("#10140a"))
        p.restore()

    @staticmethod
    def _pastilla(p, r, texto, fondo, color_texto):
        f = QFont(p.font())
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        ancho = p.fontMetrics().horizontalAdvance(texto) + 18
        caja = QRectF(r.right() - ancho - 8, r.top() + 8, ancho, 20)
        p.setPen(Qt.NoPen)
        p.setBrush(fondo)
        p.drawRoundedRect(caja, 10, 10)
        p.setPen(color_texto)
        p.drawText(caja, Qt.AlignCenter, texto)

    def _pintar_tarea(self, p, r, t):
        velo = QPainterPath()
        velo.addRoundedRect(r, 10, 10)
        p.fillPath(velo, QColor(8, 10, 16, 185))
        c = r.center()
        radio = max(16.0, min(r.height() * 0.2, 30.0))
        aro = QRectF(c.x() - radio, c.y() - radio - 8, 2 * radio, 2 * radio)
        f = QFont(p.font())
        if t.estado == t.COLA:
            f.setPixelSize(13)
            f.setBold(True)
            p.setFont(f)
            texto = "En cola" + (f"  ·  #{t.posicion}" if t.posicion else "")
            ancho = p.fontMetrics().horizontalAdvance(texto) + 28
            caja = QRectF(c.x() - ancho / 2, c.y() - 15, ancho, 30)
            p.setPen(QPen(QColor("#4b5170"), 1))
            p.setBrush(QColor("#1d2130"))
            p.drawRoundedRect(caja, 15, 15)
            p.setPen(QColor("#d6daea"))
            p.drawText(caja, Qt.AlignCenter, texto)
            return
        grosor = 5
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 40), grosor))
        p.drawEllipse(aro)
        pluma = QPen(QColor(ROJO if t.estado == t.ERROR else ACENTO), grosor)
        pluma.setCapStyle(Qt.RoundCap)
        p.setPen(pluma)
        if t.fraccion is None:  # sin total: un arco que gira (la ventana repinta mientras haya tareas)
            angulo = int(time.monotonic() * 360) % 360
            p.drawArc(aro, -angulo * 16, 100 * 16)
            texto = "…"
        else:
            p.drawArc(aro, 90 * 16, -int(360 * 16 * t.fraccion))
            texto = f"{int(t.fraccion * 100)}%"
        f.setPixelSize(max(11, int(radio * 0.55)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(aro, Qt.AlignCenter, texto)
        f.setPixelSize(12)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor("#d6ccff"))
        nombre = {"Descargar": "Descargando", "Optimizar": "Optimizando", "Reflejar": "Reflejando",
                  "Aplicar": "Aplicando"}.get(t.nombre_etapa, t.nombre_etapa)
        p.drawText(QRectF(r.left(), aro.bottom() + 6, r.width(), 18), Qt.AlignCenter, nombre)


# ---------------------------------------------------------------- aviso de «aplicado»
class AvisoAplicado(QWidget):
    """Aviso flotante abajo a la derecha de la pantalla: miniatura, «✔ Fondo aplicado» y botones.
    No roba el foco; se va solo a los `segundos` (no mientras el mouse está encima)."""

    def __init__(self, miniatura, titulo, al_volver=None, al_deshacer=None, segundos=9):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(f"""
            QFrame#aviso {{ background: #161a26; border: 1px solid #3d6b12; border-radius: 16px; }}
            QFrame#aviso QLabel {{ background: transparent; }}
            QLabel#av_mini {{ background: #0b0d13; border-radius: 10px; }}
            QLabel#av_marca {{ color: {VERDE}; font-size: 11px; font-weight: 800; letter-spacing: 1px; }}
            QLabel#av_titulo {{ color: #ffffff; font-size: 15px; font-weight: 700; }}
            QLabel#av_texto {{ color: {GRIS}; font-size: 12px; }}
            QPushButton#av_cerrar {{ background: transparent; border: none; color: #6b7189; font-size: 14px;
                                     min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
                                     border-radius: 12px; padding: 0; }}
            QPushButton#av_cerrar:hover {{ background: #2c3249; color: white; }}
            QPushButton {{ padding: 7px 14px; font-size: 12px; border-radius: 9px; }}
        """)
        exterior = QVBoxLayout(self)
        exterior.setContentsMargins(18, 18, 18, 18)  # aire para la sombra
        caja = QFrame(objectName="aviso")
        sombra = QGraphicsDropShadowEffect(caja)
        sombra.setBlurRadius(30)
        sombra.setOffset(0, 8)
        sombra.setColor(QColor(0, 0, 0, 170))
        caja.setGraphicsEffect(sombra)
        exterior.addWidget(caja)
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(14, 14, 12, 14)
        fila.setSpacing(14)
        mini = QLabel(objectName="av_mini")
        mini.setFixedSize(160, 90)
        pm = portada(miniatura, 160, 90, 10)
        if pm:
            mini.setPixmap(pm)
        fila.addWidget(mini, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        cabeza = QHBoxLayout()
        cabeza.addWidget(QLabel("✔  FONDO APLICADO", objectName="av_marca"))
        cabeza.addStretch()
        cerrar = QPushButton("✕", objectName="av_cerrar")
        cerrar.setCursor(Qt.PointingHandCursor)
        cerrar.clicked.connect(self.close)
        cabeza.addWidget(cerrar)
        col.addLayout(cabeza)
        t = QLabel(objectName="av_titulo")
        t.setFixedWidth(250)
        t.setText(t.fontMetrics().elidedText(titulo, Qt.ElideRight, 250))
        col.addWidget(t)
        col.addWidget(QLabel("Ya está en tu escritorio.", objectName="av_texto"))
        col.addStretch()
        botones = QHBoxLayout()
        botones.setSpacing(8)
        botones.addStretch()
        if al_deshacer:
            b = QPushButton("Deshacer")
            b.setToolTip("Volver al fondo que tenías antes")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda: (self.close(), al_deshacer()))
            botones.addWidget(b)
        if al_volver:
            b = QPushButton("Volver a mis ventanas", objectName="primary")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda: (self.close(), al_volver()))
            botones.addWidget(b)
        col.addLayout(botones)
        fila.addLayout(col, 1)

        self._reloj = QTimer(self, singleShot=True, interval=segundos * 1000)
        self._reloj.timeout.connect(self.close)

    def mostrar(self):
        self.adjustSize()
        area = QApplication.primaryScreen().availableGeometry()
        fin = QPoint(area.right() - self.width() + 4, area.bottom() - self.height() + 4)
        self.move(fin + QPoint(0, 24))
        self.setWindowOpacity(0.0)
        self.show()
        self._anims = []
        for prop, desde, hasta in ((b"pos", fin + QPoint(0, 24), fin), (b"windowOpacity", 0.0, 1.0)):
            a = QPropertyAnimation(self, prop, self)
            a.setDuration(260)
            a.setStartValue(desde)
            a.setEndValue(hasta)
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.start()
            self._anims.append(a)
        self._reloj.start()

    def enterEvent(self, e):
        self._reloj.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._reloj.start(4000)
        super().leaveEvent(e)


# ---------------------------------------------------------------- barra de tareas de Windows
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(texto):
    g = _GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(texto), ctypes.byref(g))
    return g


class BarraTareasWindows:
    """El botón de la ventana en la barra de tareas como barra de progreso (ITaskbarList3, por COM).
    Si Windows no lo permite, no hace nada."""
    _CLSID = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
    _IID = "{ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf}"
    ESTADOS = {"nada": 0, "esperando": 1, "normal": 2, "error": 4, "pausa": 8}

    def __init__(self):
        self._p = None
        self._roto = False

    def _metodo(self, i, *args):
        vtbl = ctypes.cast(self._p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *args)(vtbl[i])

    def _listo(self):
        if self._p or self._roto:
            return bool(self._p)
        try:
            ctypes.windll.ole32.CoInitialize(None)  # Qt ya lo hizo: esto solo suma una referencia
            p = ctypes.c_void_p()
            hr = ctypes.windll.ole32.CoCreateInstance(ctypes.byref(_guid(self._CLSID)), None, 1,  # INPROC_SERVER
                                                      ctypes.byref(_guid(self._IID)), ctypes.byref(p))
            if hr != 0 or not p.value:
                self._roto = True
                return False
            self._p = p.value
            self._metodo(3)(self._p)  # HrInit
            return True
        except OSError:
            self._roto = True
            return False

    def poner(self, hwnd, fraccion=None, estado="normal"):
        """estado: nada | esperando (sin total) | normal | error | pausa."""
        if not hwnd or not self._listo():
            return
        try:
            self._metodo(10, wintypes.HWND, ctypes.c_int)(self._p, hwnd, self.ESTADOS[estado])  # SetProgressState
            if fraccion is not None and estado in ("normal", "error", "pausa"):
                self._metodo(9, wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong)(  # SetProgressValue
                    self._p, hwnd, int(fraccion * 1000), 1000)
        except OSError:
            self._roto = True
