"""Instalar / actualizar / desinstalar en la PC actual, solo para el usuario (sin administrador).

Dos modos (Instalacion(modo=...)):
  «exe»     el .exe es portable: al abrirlo desde un USB ofrece instalarse (o actualizar la copia
            instalada) y, si se prefiere, "Solo abrir". Se instala copiando ese mismo .exe.
  «carpeta» el .exe de Release es solo un instalador: trae dentro app.zip (la app compilada como carpeta,
            PyInstaller --onedir, que abre mucho más rápido que un onefile) y reemplaza los archivos del
            programa en la carpeta instalada sin tocar ajustes ni nada más. Ver instalador.py.
La copia instalada vive en %LocalAppData%\\GigaTech\\<Programa>, queda en el menú Inicio, en «Aplicaciones
instaladas» de Windows y puede arrancar con Windows. Se desinstala desde Windows o desde el ícono junto al reloj.

También muestra las novedades: CHANGELOG.md va dentro del .exe («## versión — fecha» y debajo «- cambio»);
«Novedades…» en la bandeja abre el historial y la copia instalada avisa una vez cuando cambió de versión.

Este archivo es idéntico en GigaWalls y Grabador de pantalla: lo único que cambia es la
configuración al final (INSTALACION = Instalacion(...)). Si se corrige uno, copiar al otro.
"""
import os
import shutil
import subprocess
import sys
import time
import winreg

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


def _ps(script):
    """Ejecuta un comando de PowerShell sin ventana."""
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=CREATE_NO_WINDOW, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def _q(texto):
    """Escapa un texto para ponerlo entre comillas simples de PowerShell."""
    return str(texto).replace("'", "''")


def _version(texto):
    try:
        return tuple(int(p) for p in str(texto).split("."))
    except ValueError:
        return (0,)


_ACENTO = "#7c5cff"  # color del botón principal (lo fija Instalacion(acento=...))


def leer_novedades():
    """CHANGELOG.md (dentro del .exe, o junto al código): [(versión, fecha, [cambios])], la más nueva primero."""
    import re
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    entradas = []
    try:
        with open(os.path.join(base, "CHANGELOG.md"), encoding="utf-8") as f:
            for linea in f:
                m = re.match(r"^##\s+(\d+\.\d+\.\d+)\s*(?:[—–-]\s*(.*))?$", linea.strip())
                if m:
                    entradas.append((m[1], (m[2] or "").strip(), []))
                elif entradas and linea.lstrip().startswith("- "):
                    entradas[-1][2].append(linea.lstrip()[2:].strip())
    except OSError:
        pass
    return entradas


def _barra_oscura(widget):
    """Barra de título oscura (Windows 10 20H1+ / 11). Si no se puede, queda la clara."""
    try:
        import ctypes
        valor = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(int(widget.winId())), 20, ctypes.byref(valor), ctypes.sizeof(valor))
    except (OSError, AttributeError):
        pass


def _caja(icono, titulo, texto, detalle, botones, chip="", lista=None):
    """Cuadro con el estilo oscuro de la app y botones propios. Devuelve el texto del botón elegido.

    El primer botón es el principal (relleno de color). Los de rol Destructive se ven rojos al pasar
    el ratón. `icono` (QMessageBox.Warning...) solo cambia el color del chip de versión. `lista`: entradas de
    leer_novedades() para mostrar debajo, con desplazamiento."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                                   QScrollArea, QVBoxLayout, QWidget)
    d = QDialog()
    d.setWindowTitle(titulo)
    d.setWindowFlags(d.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    d.setMinimumWidth(500)
    aviso = icono == QMessageBox.Warning
    color = "#d9455f" if aviso else _ACENTO  # al desinstalar, el botón principal es rojo

    def mezcla(c1, c2, t):
        """c1 y c2 «#rrggbb» mezclados (t = cuánto de c2): el chip toma el color de la app sobre el fondo."""
        a, b = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (c1, c2))
        return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))
    chip_fondo, chip_borde, chip_texto = mezcla("#141824", color, .18), mezcla("#141824", color, .5), mezcla(color, "#ffffff", .55)
    d.setStyleSheet(f"""
        QDialog {{ background: #141824; }}
        QLabel {{ color: #e6e8f0; font-family: 'Nunito', 'Segoe UI Variable Text', 'Segoe UI'; font-size: 13px; }}
        QLabel#titulo {{ font-size: 19px; font-weight: 700; color: #ffffff; }}
        QLabel#detalle {{ color: #8a90a6; }}
        QLabel#chip {{ background: {chip_fondo}; color: {chip_texto}; border: 1px solid {chip_borde}; border-radius: 11px;
                       padding: 3px 12px; font-size: 12px; font-weight: 600; }}
        QPushButton {{ font-family: 'Nunito', 'Segoe UI Variable Text', 'Segoe UI'; font-size: 13px; color: #e6e8f0;
                       background: #1d2130; border: 1px solid #2c3249; border-radius: 10px;
                       padding: 9px 20px; min-width: 90px; }}
        QPushButton:hover {{ background: #262b3f; border-color: #3a4160; }}
        QPushButton#principal {{ background: {color}; border: 2px solid {color}; color: white; font-weight: 600; }}
        QPushButton#principal:hover {{ border-color: #ffffff60; }}
        QPushButton#peligro:hover {{ background: #3a1f2a; border-color: #6b2a3f; color: #ff7a93; }}
        QScrollArea {{ background: transparent; border: none; }}
        QWidget#lista {{ background: transparent; }}
        QLabel#version {{ color: {_ACENTO}; font-weight: 700; font-size: 13px; margin-top: 8px; }}
        QLabel#cambio {{ color: #c9cdda; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; }}
        QScrollBar::handle:vertical {{ background: #2c3249; border-radius: 4px; min-height: 30px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    """)
    raiz = QVBoxLayout(d)
    raiz.setContentsMargins(28, 26, 28, 22)
    raiz.setSpacing(20)

    cabeza = QHBoxLayout()
    cabeza.setSpacing(18)
    logo = QLabel()
    icono_app = QApplication.windowIcon()
    if not icono_app.isNull():
        logo.setPixmap(icono_app.pixmap(64, 64))
        logo.setAlignment(Qt.AlignTop)
        cabeza.addWidget(logo)
    textos = QVBoxLayout()
    textos.setSpacing(8)
    t = QLabel(texto, objectName="titulo")
    t.setWordWrap(True)
    textos.addWidget(t)
    if chip:
        from PySide6.QtWidgets import QSizePolicy
        fila = QHBoxLayout()
        et_chip = QLabel(chip, objectName="chip")
        et_chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)  # que no se estire en alto
        fila.addWidget(et_chip)
        fila.addStretch()
        textos.addLayout(fila)
    if detalle:
        dt = QLabel(detalle, objectName="detalle")
        dt.setWordWrap(True)
        textos.addWidget(dt)
    cabeza.addLayout(textos, 1)
    raiz.addLayout(cabeza)

    if lista:
        cont = QWidget(objectName="lista")
        capa = QVBoxLayout(cont)
        capa.setContentsMargins(82, 0, 10, 0)  # alineado con el texto (a la derecha del logo)
        capa.setSpacing(3)
        for version, fecha, cambios in lista:
            capa.addWidget(QLabel(version + (f"  ·  {fecha}" if fecha else ""), objectName="version"))
            for c in cambios:
                et = QLabel(f"•  {c}", objectName="cambio")
                et.setWordWrap(True)
                capa.addWidget(et)
        capa.addStretch()
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(cont)
        area.setMinimumHeight(min(340, 60 + 26 * sum(1 + len(e[2]) for e in lista)))
        area.setMaximumHeight(340)
        raiz.addWidget(area)

    fila = QHBoxLayout()
    fila.setSpacing(10)
    fila.addStretch()
    elegido = {"texto": ""}
    principal = None
    # el principal va a la derecha (donde Windows pone «Aceptar»); los demás a su izquierda
    for i, (txt, rol) in reversed(list(enumerate(botones))):
        b = QPushButton(txt)
        if i == 0:
            b.setObjectName("principal")
            principal = b
        elif rol == QMessageBox.DestructiveRole:
            b.setObjectName("peligro")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda _=False, txt=txt: (elegido.update(texto=txt), d.accept()))
        fila.addWidget(b)
    raiz.addLayout(fila)
    if principal:
        principal.setDefault(True)
        principal.setFocus()
    _barra_oscura(d)
    d.exec()
    return elegido["texto"]


_PUENTES = set()  # puentes hilo -> Qt vivos (si no se guardan, Python los borra antes de que respondan)


def _en_hilo(fn, listo, progreso=None):
    """Corre fn() en un hilo aparte y llama listo(resultado, error) en el hilo de Qt.
    fn puede recibir `avance(hecho, total)` si se pasa `progreso` (también se llama en el hilo de Qt)."""
    import threading
    from PySide6.QtCore import QObject, Signal

    class _Puente(QObject):
        hecho = Signal(object, object)
        avance = Signal(object, object)

    p = _Puente()
    _PUENTES.add(p)
    p.hecho.connect(lambda r, e: (_PUENTES.discard(p), listo(r, e)))
    if progreso:
        p.avance.connect(progreso)

    def correr():
        try:
            r, e = (fn(p.avance.emit) if progreso else fn()), None
        except Exception as ex:  # noqa: BLE001
            r, e = None, ex
        try:
            p.hecho.emit(r, e)
        except RuntimeError:
            pass  # la app ya se cerró mientras el hilo trabajaba: nadie espera la respuesta
    threading.Thread(target=correr, daemon=True).start()


def _pedir_github(url, timeout=20):
    import urllib.request
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "GigaTech-actualizador"})
    return urllib.request.urlopen(req, timeout=timeout)


class Instalacion:
    def __init__(self, titulo, exe, clave, valor_run, version, arg_inicio="--minimized",
                 descripcion="", datos=(), acento=None, conserva="Tus ajustes", modo="exe", arranque=True,
                 bandeja=True, nota_desinstalar="", repo=None):
        self.titulo = titulo            # nombre visible: «GigaWalls»
        self.exe_nombre = exe           # «GigaWalls.exe»
        self.clave = clave              # subclave en «Aplicaciones instaladas»
        self.valor_run = valor_run      # nombre del valor de arranque con Windows
        self.version = version          # «1.0.0»
        self.arg_inicio = arg_inicio    # argumentos al arrancar con Windows
        self.descripcion = descripcion
        self.datos = tuple(datos)       # archivos de ajustes junto al .exe que se llevan al instalar
        self.conserva = conserva        # lo que se mantiene al actualizar: «Tus ajustes y tu biblioteca»
        self.modo = modo                # «exe» (portable que se copia) o «carpeta» (instalador con app.zip)
        self.arranque = arranque        # al instalar, que arranque con Windows
        self.bandeja = bandeja          # la app tiene ícono junto al reloj (con «Desinstalar…»)
        self.nota_desinstalar = nota_desinstalar  # lo que se aclara al desinstalar («Tus videos no se borran»)
        self.repo = repo                # «Usuario/Repo» público de GitHub con las versiones en Releases
        self._buscando = False
        self._pospuesta = None          # versión a la que se respondió «Más tarde» (no se vuelve a avisar sola)
        self._reloj = None
        self.salir = None               # la app pone aquí su salida ordenada (se usa al actualizar)
        if acento:                      # color del botón principal de los cuadros (el de la app)
            global _ACENTO
            _ACENTO = acento

    # ---------- rutas ----------
    @property
    def carpeta(self):
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "GigaTech", os.path.splitext(self.exe_nombre)[0])

    @property
    def exe(self):
        return os.path.join(self.carpeta, self.exe_nombre)

    @property
    def _acceso(self):
        programas = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
        return os.path.join(programas, f"{self.titulo}.lnk")

    # ---------- estado ----------
    @property
    def publicada(self):
        """True si corre como .exe empaquetado (el código fuente no ofrece instalarse)."""
        return bool(getattr(sys, "frozen", False))

    @property
    def ruta_actual(self):
        return os.path.abspath(sys.executable)

    @property
    def corriendo_instalada(self):
        return os.path.normcase(self.ruta_actual) == os.path.normcase(self.exe)

    @property
    def instalada(self):
        return os.path.isfile(self.exe)

    @property
    def _zip(self):
        """Modo carpeta: el paquete con la app que lleva dentro el instalador (None si esto no es el instalador)."""
        ruta = os.path.join(getattr(sys, "_MEIPASS", ""), "app.zip")
        return ruta if self.modo == "carpeta" and os.path.isfile(ruta) else None

    def _texto_info(self):
        partes = ["Se instala solo para este usuario (no pide administrador)"]
        partes.append(", arranca con Windows y queda en el menú Inicio" if self.arranque else " y queda en el menú Inicio")
        donde = "desde Aplicaciones de Windows" + (" o desde su ícono junto al reloj" if self.bandeja else "")
        return f"{partes[0]}{partes[1]}. Se desinstala {donde}."

    @property
    def version_instalada(self):
        if not self.instalada:
            return None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{UNINSTALL_KEY}\\{self.clave}") as k:
                return _version(winreg.QueryValueEx(k, "DisplayVersion")[0])
        except OSError:
            return (0,)

    # ---------- arranque con Windows ----------
    @property
    def inicia_con_windows(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, self.valor_run)
                return True
        except OSError:
            return False

    def comando_inicio(self, exe=None):
        return f'"{exe or self.ruta_actual}" {self.arg_inicio}'.strip()

    def iniciar_con_windows(self, si, exe=None):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if si:
                winreg.SetValueEx(k, self.valor_run, 0, winreg.REG_SZ, self.comando_inicio(exe))
            else:
                try:
                    winreg.DeleteValue(k, self.valor_run)
                except OSError:
                    pass

    # ---------- instalar ----------
    @property
    def _nombre_evento(self):
        return f"Local\\GigaTech.{self.clave}.Cerrar"

    def escuchar_cierre(self, salir):
        """La app abierta atiende el pedido de cierre del instalador (un evento de Windows con nombre) y sale
        por su cuenta con `salir`: así quita su ícono de la bandeja. Si la mataban, Windows dejaba un ícono
        fantasma junto al reloj hasta pasarle el mouse."""
        import ctypes
        from PySide6.QtCore import QTimer
        k = ctypes.windll.kernel32
        k.CreateEventW.restype = ctypes.c_void_p
        h = k.CreateEventW(None, True, False, self._nombre_evento)  # reinicio manual, empieza apagado
        if not h:
            return
        k.ResetEvent(ctypes.c_void_p(h))  # por si quedó encendido de una actualización anterior
        self._evento_cierre = h

        def revisar():
            if k.WaitForSingleObject(ctypes.c_void_p(h), 0) == 0:  # WAIT_OBJECT_0: lo pidió el instalador
                self._reloj_cierre.stop()
                salir()
        self._reloj_cierre = QTimer()
        self._reloj_cierre.timeout.connect(revisar)
        self._reloj_cierre.start(400)

    def cerrar_otras(self):
        """Cierra las copias instaladas que estén abiertas y lo que corra desde su carpeta (no se puede
        reemplazar un archivo en uso). Primero les pide que salgan solas (escuchar_cierre) y espera unos
        segundos; lo que siga abierto después se cierra a la fuerza."""
        import ctypes
        k = ctypes.windll.kernel32
        k.OpenEventW.restype = ctypes.c_void_p
        h = k.OpenEventW(0x0002, False, self._nombre_evento)  # EVENT_MODIFY_STATE; None si nadie escucha
        if h:
            k.SetEvent(ctypes.c_void_p(h))
        yo = f"{os.getpid()},{os.getppid()}"  # el proceso y su lanzador (onefile)
        dentro = _q(os.path.join(self.carpeta, ""))
        filtro = (f"Get-Process | Where-Object {{ $_.Path -and ($_.Path -eq '{_q(self.exe)}' -or "
                  f"$_.Path.StartsWith('{dentro}', [StringComparison]::OrdinalIgnoreCase)) -and $_.Id -notin @({yo}) }}")
        espera = f"{filtro} | Wait-Process -Timeout 8 -ErrorAction SilentlyContinue; " if h else ""
        _ps(f"{espera}{filtro} | Stop-Process -Force -ErrorAction SilentlyContinue")
        if h:
            k.ResetEvent(ctypes.c_void_p(h))  # que la copia nueva no lo encuentre encendido al abrir
            k.CloseHandle(ctypes.c_void_p(h))
        time.sleep(0.8)

    @staticmethod
    def _reintentar(fn, segundos=10):
        """Un proceso recién cerrado tarda un poco en soltar sus archivos: reintenta hasta `segundos`."""
        fin = time.monotonic() + segundos
        while True:
            try:
                return fn()
            except OSError:
                if time.monotonic() > fin:
                    raise
                time.sleep(0.3)

    def _instalar_carpeta(self):
        """Modo carpeta: reemplaza solo los archivos del programa (los que trae app.zip: el .exe y _internal)."""
        import zipfile
        temporal = os.path.join(self.carpeta, "_nuevo")
        shutil.rmtree(temporal, ignore_errors=True)
        with zipfile.ZipFile(self._zip) as z:
            z.extractall(temporal)
        nuevos = os.listdir(temporal)
        if self.exe_nombre not in nuevos:
            raise RuntimeError(f"El paquete no trae {self.exe_nombre}.")
        protegidos = {n.lower() for n in (*self.datos, "version_vista.txt", "_nuevo")}
        for nombre in nuevos:
            if nombre.lower() in protegidos:  # nunca pisar ajustes del usuario
                continue
            destino = os.path.join(self.carpeta, nombre)
            if os.path.isdir(destino):
                self._reintentar(lambda d=destino: shutil.rmtree(d))
            elif os.path.exists(destino):
                self._reintentar(lambda d=destino: os.remove(d))
            self._reintentar(lambda n=nombre, d=destino: os.replace(os.path.join(temporal, n), d))
        shutil.rmtree(temporal, ignore_errors=True)

    def instalar(self):
        origen = self.ruta_actual
        anterior = self.version_instalada
        self.cerrar_otras()
        os.makedirs(self.carpeta, exist_ok=True)
        if anterior and not os.path.exists(self._version_vista):
            # Instalada por una versión que aún no guardaba version_vista.txt: que avise de lo nuevo igual
            try:
                with open(self._version_vista, "w", encoding="utf-8") as f:
                    f.write(".".join(map(str, anterior)))
            except OSError:
                pass
        if self._zip:
            self._instalar_carpeta()
        else:
            self._reintentar(lambda: shutil.copy2(origen, self.exe))
        for nombre in self.datos:  # lleva los ajustes del .exe portable, sin pisar los ya instalados
            src, dst = os.path.join(os.path.dirname(origen), nombre), os.path.join(self.carpeta, nombre)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
        _ps("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
            "$s.TargetPath='{exe}';$s.WorkingDirectory='{dir}';$s.Description='{desc}';$s.Save()".format(
                lnk=_q(self._acceso), exe=_q(self.exe), dir=_q(self.carpeta),
                desc=_q(self.descripcion or self.titulo)))
        if self.arranque:
            self.iniciar_con_windows(True, self.exe)  # la copia instalada, no la del USB
        self._registrar()

    def _registrar(self):
        """Entrada en «Aplicaciones instaladas» (solo usuario actual)."""
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{UNINSTALL_KEY}\\{self.clave}") as k:
            def txt(n, v): winreg.SetValueEx(k, n, 0, winreg.REG_SZ, v)
            def num(n, v): winreg.SetValueEx(k, n, 0, winreg.REG_DWORD, v)
            txt("DisplayName", f"{self.titulo} · GigaTech")
            txt("DisplayVersion", self.version)
            txt("Publisher", "GigaTech")
            txt("DisplayIcon", f'"{self.exe}",0')
            txt("InstallLocation", self.carpeta)
            txt("UninstallString", f'"{self.exe}" --desinstalar')
            num("NoModify", 1)
            num("NoRepair", 1)
            tam = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(self.carpeta) for f in fs)
            num("EstimatedSize", int(tam / 1024))

    def abrir_instalada(self, aviso=None):
        """Lanza la copia instalada (con «--instalado» o «--reinstalado» para que lo confirme). Devuelve True:
        esta instancia debe cerrarse."""
        env = {k: v for k, v in os.environ.items() if k != "_MEIPASS2" and not k.startswith("_PYI")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # que no reutilice la carpeta temporal de esta
        args = [a for a in sys.argv[1:] if a != "--instalar"] + ([aviso] if aviso else [])
        subprocess.Popen([self.exe, *args], env=env, cwd=self.carpeta, close_fds=True,
                         creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)
        return True

    def ofrecer(self, detalle_desinstalar=""):
        """Al abrir el .exe publicado fuera de su carpeta de instalación muestra el estado de la PC y
        ofrece, según el caso: instalar, actualizar, reinstalar, desinstalar o abrir la copia instalada.
        Devuelve True si esta instancia debe cerrarse (se abrió la instalada o se desinstaló)."""
        if not self.publicada or self.corriendo_instalada:
            return False
        if self.modo == "carpeta" and not self._zip:
            return False  # la app compilada en carpeta (no el instalador): corre tal cual, sin ofrecer nada
        from PySide6.QtWidgets import QMessageBox
        detalle_desinstalar = detalle_desinstalar or self.nota_desinstalar
        solo_instalador = self._zip is not None  # sin «Solo abrir»: este .exe no trae la app para correr suelta
        instalada = self.version_instalada
        nueva = _version(self.version)
        elegido = ""
        txt_inst = ".".join(map(str, instalada)) if instalada is not None else ""
        if "--instalar" in sys.argv:  # instalación por script, sin preguntar
            if instalada is not None and instalada >= nueva:
                return self.abrir_instalada()
        else:
            info = self._texto_info()
            if instalada is None:
                titulo, texto = f"Instalar {self.titulo}", f"Instalar {self.titulo} en esta PC"
                chip = f"Versión {self.version}"
                botones = [("Instalar", QMessageBox.AcceptRole)]
                if not solo_instalador:
                    botones.append(("Solo abrir", QMessageBox.RejectRole))
            elif instalada < nueva:
                titulo, texto = f"Actualizar {self.titulo}", f"Hay una versión nueva de {self.titulo}"
                chip = f"{txt_inst}  →  {self.version}"
                info = f"Se reemplaza la versión instalada. {self.conserva} se conservan."
                botones = [("Actualizar", QMessageBox.AcceptRole), ("Desinstalar", QMessageBox.DestructiveRole)]
            elif instalada == nueva:
                titulo, texto = self.titulo, "Ya tienes la versión más actual"
                chip = f"✔  {txt_inst} instalada"
                info = "Puedes abrirla, reinstalarla si algo falla, o quitarla de esta PC."
                botones = [("Abrir", QMessageBox.AcceptRole), ("Reinstalar", QMessageBox.ActionRole),
                           ("Desinstalar", QMessageBox.DestructiveRole)]
            else:
                titulo, texto = self.titulo, "Ya tienes una versión más nueva instalada"
                chip = f"Instalada {txt_inst}  ·  este archivo {self.version}"
                info = "Se abrirá la versión instalada. Este archivo es antiguo y se puede borrar."
                botones = [("Abrir", QMessageBox.AcceptRole), ("Desinstalar", QMessageBox.DestructiveRole)]
            elegido = _caja(QMessageBox.Question, titulo, texto, info, botones, chip)
            if elegido == "Abrir":
                return self.abrir_instalada()
            if elegido == "Desinstalar":
                self.desinstalar(detalle_desinstalar)
                return True  # desinstalada o cancelada: este archivo solo se usó como instalador
            if elegido not in ("Instalar", "Actualizar", "Reinstalar"):
                # «Solo abrir» (o se cerró el cuadro): si ya hay una copia instalada, no abrir otra encima
                return elegido != "Solo abrir"
        try:
            self.instalar()
        except Exception as e:  # noqa: BLE001
            _caja(QMessageBox.Warning, f"Instalar {self.titulo}",
                  "No se pudo instalar." if solo_instalador else "No se pudo instalar. Se abre sin instalar.",
                  str(e), [("Aceptar", QMessageBox.AcceptRole)])
            return solo_instalador
        # Al actualizar no hace falta: la copia instalada nota sola que cambió de versión (avisar_novedades).
        return self.abrir_instalada({"Instalar": "--instalado", "Reinstalar": "--reinstalado"}.get(elegido))

    # ---------- novedades ----------
    @property
    def _version_vista(self):
        return os.path.join(self.carpeta, "version_vista.txt")

    def avisar_novedades(self):
        """Al arrancar la copia instalada: confirma la instalación o, si cambió de versión desde la última vez
        (por el menú de actualizar, por release o como sea), muestra una vez lo nuevo. Llamar con la app ya creada."""
        if not self.corriendo_instalada:
            return
        from PySide6.QtWidgets import QMessageBox
        try:
            with open(self._version_vista, encoding="utf-8") as f:
                vista = f.read().strip()
        except OSError:
            vista = ""
        try:
            with open(self._version_vista, "w", encoding="utf-8") as f:
                f.write(self.version)
        except OSError:
            pass
        ok = [("Entendido", QMessageBox.AcceptRole)]
        if "--instalado" in sys.argv:
            _caja(QMessageBox.Information, f"{self.titulo} instalado", f"{self.titulo} quedó instalado en esta PC",
                  ("Arranca con Windows y está en el menú Inicio." if self.arranque else "Está en el menú Inicio.") +
                  " Se desinstala desde Aplicaciones de Windows" +
                  (" o desde su ícono junto al reloj." if self.bandeja else "."), ok, f"✔  {self.version} instalada")
        elif "--reinstalado" in sys.argv:
            _caja(QMessageBox.Information, f"{self.titulo} reinstalado", f"{self.titulo} se reinstaló",
                  "Tus ajustes siguen como estaban.", ok, f"✔  {self.version} instalada")
        elif vista and _version(vista) < _version(self.version):
            nuevas = [e for e in leer_novedades() if _version(vista) < _version(e[0]) <= _version(self.version)]
            _caja(QMessageBox.Information, f"{self.titulo} actualizado", f"{self.titulo} se actualizó",
                  "Tus ajustes siguen como estaban." + (" Esto es lo nuevo:" if nuevas else ""), ok,
                  f"{vista}  →  {self.version}", lista=nuevas)

    def ver_novedades(self):
        """«Novedades…» de la bandeja: el historial completo."""
        from PySide6.QtWidgets import QMessageBox
        _caja(QMessageBox.Information, f"Novedades de {self.titulo}", f"Novedades de {self.titulo}",
              "Lo que cambió en cada versión, la más nueva arriba.", [("Entendido", QMessageBox.AcceptRole)],
              f"Versión {self.version}", lista=leer_novedades() or None)

    def acerca_de(self, extra=""):
        """«Acerca de…»: nombre, versión, qué es, dónde está instalado y acceso a las novedades.
        `extra`: líneas propias de la app (dónde guarda sus datos, etc.)."""
        from PySide6.QtWidgets import QMessageBox
        if self.corriendo_instalada:
            donde = f"Instalado en {self.carpeta}"
        elif self.publicada:
            donde = f"Copia sin instalar: {os.path.dirname(self.ruta_actual)}"
        else:
            donde = "Ejecutándose desde el código fuente"
        detalle = "\n\n".join(p for p in (self.descripcion or self.titulo, extra, donde, "© GigaTech") if p)
        botones = [("Cerrar", QMessageBox.AcceptRole), ("Novedades…", QMessageBox.ActionRole)]
        if self.repo:
            botones.append(("Buscar actualizaciones", QMessageBox.ActionRole))
        elegido = _caja(QMessageBox.Information, f"Acerca de {self.titulo}", self.titulo, detalle, botones,
                        f"Versión {self.version}")
        if elegido == "Novedades…":
            self.ver_novedades()
        elif elegido == "Buscar actualizaciones":
            self.buscar_actualizacion(manual=True)

    # ---------- actualizar desde GitHub ----------
    def ultima_version(self):
        """La versión publicada más nueva en GitHub Releases: dict con version, notas (lista de cambios),
        url y tamano del instalador (y sha256 si GitHub lo da). Lanza una excepción si no se puede consultar."""
        import json
        with _pedir_github(f"https://api.github.com/repos/{self.repo}/releases/latest") as r:
            datos = json.load(r)
        archivo = next((a for a in datos.get("assets", []) if a["name"].lower() == self.exe_nombre.lower()), None)
        if not archivo:
            raise RuntimeError(f"La versión publicada no trae {self.exe_nombre}.")
        digest = archivo.get("digest") or ""
        return {
            "version": datos["tag_name"].lstrip("vV"),
            "notas": [l.strip()[2:].strip() for l in (datos.get("body") or "").splitlines()
                      if l.strip().startswith("- ")],
            "url": archivo["browser_download_url"],
            "tamano": archivo.get("size") or 0,
            "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else "",
        }

    def actualizar_automaticamente(self, primera=20, cada_horas=6):
        """Revisa en segundo plano a los `primera` segundos y luego cada `cada_horas` (la app puede quedar
        abierta días). Solo la copia instalada; avisa únicamente si hay una versión nueva."""
        if not self.repo or not self.corriendo_instalada:
            return
        import glob
        import tempfile
        from PySide6.QtCore import QTimer
        # instaladores que bajó una actualización anterior (~200 MB cada uno); el que siga en uso no se borra
        for viejo in glob.glob(os.path.join(tempfile.gettempdir(), f"{os.path.splitext(self.exe_nombre)[0]}-*.exe")):
            try:
                os.remove(viejo)
            except OSError:
                pass
        QTimer.singleShot(primera * 1000, self.buscar_actualizacion)
        self._reloj = QTimer()
        self._reloj.timeout.connect(self.buscar_actualizacion)
        self._reloj.start(int(cada_horas * 3600 * 1000))

    def buscar_actualizacion(self, manual=False):
        """Consulta GitHub sin congelar la app. `manual` («Buscar actualizaciones ahora»): siempre responde,
        también si ya está al día o no hay Internet; la búsqueda automática solo habla si hay algo nuevo."""
        from PySide6.QtWidgets import QMessageBox
        ok = [("Entendido", QMessageBox.AcceptRole)]
        if not self.repo or self._buscando:
            return
        if not self.corriendo_instalada:
            if manual:
                _caja(QMessageBox.Information, "Buscar actualizaciones", "Esta copia no está instalada",
                      "Solo la copia instalada se actualiza sola. Instálala con el instalador de "
                      f"{self.titulo} y desde ahí se mantendrá al día.", ok, f"Versión {self.version}")
            return
        self._buscando = True

        def listo(info, error):
            self._buscando = False
            if error:
                if manual:
                    _caja(QMessageBox.Information, "Buscar actualizaciones", "No se pudo revisar ahora",
                          "Revisa tu conexión a Internet e inténtalo de nuevo en un rato.\n\n"
                          f"Detalle: {error}", ok, f"Versión {self.version}")
                return
            if _version(info["version"]) <= _version(self.version):
                if manual:
                    _caja(QMessageBox.Information, "Buscar actualizaciones", "Ya tienes la versión más actual",
                          f"{self.titulo} revisa solo cada pocas horas y te avisa cuando salga una nueva.",
                          ok, f"✔  {self.version} instalada")
                return
            if not manual and self._pospuesta == info["version"]:
                return  # ya dijo «Más tarde» a esta versión: no insistir hasta que la pida o salga otra
            self._ofrecer_actualizacion(info)

        _en_hilo(self.ultima_version, listo)

    def _ofrecer_actualizacion(self, info):
        from PySide6.QtWidgets import QMessageBox
        nueva = info["version"]
        mb = f" ({info['tamano'] / 1e6:.0f} MB)" if info["tamano"] else ""
        elegido = _caja(
            QMessageBox.Question, f"Actualizar {self.titulo}", f"Hay una versión nueva de {self.titulo}",
            f"Se descarga{mb}, se cierra {self.titulo} un momento y se abre la versión nueva. "
            f"{self.conserva} se conservan." + (" Esto es lo nuevo:" if info["notas"] else ""),
            [("Actualizar", QMessageBox.AcceptRole), ("Más tarde", QMessageBox.RejectRole)],
            f"{self.version}  →  {nueva}", lista=[(nueva, "", info["notas"])] if info["notas"] else None)
        if elegido != "Actualizar":
            self._pospuesta = nueva
            return
        self._descargar_e_instalar(info)

    def _descargar(self, info, destino, avance, cancelado):
        """Baja el instalador a `destino` (en el hilo aparte) y comprueba que llegó completo."""
        import hashlib
        h, hecho, parcial = hashlib.sha256(), 0, destino + ".parcial"
        try:
            with _pedir_github(info["url"], timeout=60) as r, open(parcial, "wb") as f:
                total = int(r.headers.get("Content-Length") or info["tamano"] or 0)
                while True:
                    if cancelado():
                        raise InterruptedError("cancelado")
                    bloque = r.read(1 << 18)
                    if not bloque:
                        break
                    f.write(bloque)
                    h.update(bloque)
                    hecho += len(bloque)
                    avance(hecho, total)
            if total and hecho != total:
                raise RuntimeError(f"La descarga quedó incompleta ({hecho} de {total} bytes).")
            if info["sha256"] and h.hexdigest().lower() != info["sha256"].lower():
                raise RuntimeError("El archivo descargado no coincide con el publicado (sha256).")
            os.replace(parcial, destino)
        except BaseException:
            try:
                os.remove(parcial)  # no dejar 200 MB a medias en Temp
            except OSError:
                pass
            raise
        return destino

    def _descargar_e_instalar(self, info):
        """Ventana con barra de progreso mientras baja; al terminar abre el instalador en modo «--instalar»
        (reemplaza la carpeta, conserva los ajustes y abre la copia nueva) y cierra esta."""
        import tempfile
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                                       QPushButton, QVBoxLayout)
        destino = os.path.join(tempfile.gettempdir(), f"{os.path.splitext(self.exe_nombre)[0]}-{info['version']}.exe")
        d = QDialog()
        d.setWindowTitle(f"Actualizar {self.titulo}")
        d.setWindowFlags(d.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        d.setMinimumWidth(460)
        d.setStyleSheet(f"""
            QDialog {{ background: #141824; }}
            QLabel {{ color: #e6e8f0; font-family: 'Nunito', 'Segoe UI Variable Text', 'Segoe UI'; font-size: 13px; }}
            QLabel#titulo {{ font-size: 17px; font-weight: 700; color: #ffffff; }}
            QLabel#detalle {{ color: #8a90a6; }}
            QProgressBar {{ background: #1d2130; border: 1px solid #2c3249; border-radius: 6px; height: 12px;
                            text-align: center; color: transparent; }}
            QProgressBar::chunk {{ background: {_ACENTO}; border-radius: 5px; }}
            QPushButton {{ font-family: 'Nunito', 'Segoe UI Variable Text', 'Segoe UI'; font-size: 13px; color: #e6e8f0;
                           background: #1d2130; border: 1px solid #2c3249; border-radius: 10px;
                           padding: 8px 18px; min-width: 90px; }}
            QPushButton:hover {{ background: #262b3f; border-color: #3a4160; }}
        """)
        raiz = QVBoxLayout(d)
        raiz.setContentsMargins(26, 22, 26, 20)
        raiz.setSpacing(12)
        raiz.addWidget(QLabel(f"Descargando {self.titulo} {info['version']}…", objectName="titulo"))
        barra = QProgressBar()
        barra.setRange(0, 0)  # sin total aún: animación de espera
        raiz.addWidget(barra)
        estado = QLabel("Conectando…", objectName="detalle")
        raiz.addWidget(estado)
        fila = QHBoxLayout()
        fila.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setCursor(Qt.PointingHandCursor)
        fila.addWidget(cancelar)
        raiz.addLayout(fila)
        _barra_oscura(d)
        resultado = {"cancelado": False, "error": None, "listo": False}
        cancelar.clicked.connect(lambda: (resultado.update(cancelado=True), d.reject()))

        def avance(hecho, total):
            if total:
                barra.setRange(0, 1000)
                barra.setValue(int(1000 * hecho / total))
                estado.setText(f"{hecho / 1e6:.0f} de {total / 1e6:.0f} MB")

        def listo(_, error):
            resultado.update(listo=error is None, error=error)
            d.accept()

        _en_hilo(lambda av: self._descargar(info, destino, av, lambda: resultado["cancelado"]), listo, avance)
        d.exec()
        if resultado["cancelado"]:
            return
        if not resultado["listo"]:
            _caja(QMessageBox.Information, f"Actualizar {self.titulo}", "No se pudo descargar la actualización",
                  f"{self.titulo} sigue funcionando con la versión {self.version}. Puedes intentarlo de nuevo "
                  f"desde «Buscar actualizaciones».\n\nDetalle: {resultado['error']}",
                  [("Entendido", QMessageBox.AcceptRole)], f"{self.version}  →  {info['version']}")
            return
        env = {k: v for k, v in os.environ.items() if k != "_MEIPASS2" and not k.startswith("_PYI")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        subprocess.Popen([destino, "--instalar"], env=env, cwd=tempfile.gettempdir(), close_fds=True,
                         creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)
        # la salida ordenada de la app si la dio (detener el fondo, etc.); el instalador igual cierra lo que quede
        (self.salir or QApplication.instance().quit)()

    # ---------- desinstalar ----------
    def quitar(self):
        """Quita arranque, acceso, entrada de Aplicaciones y la carpeta instalada (con sus ajustes)."""
        self.iniciar_con_windows(False)
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{UNINSTALL_KEY}\\{self.clave}")
        except OSError:
            pass
        try:
            os.remove(self._acceso)
        except OSError:
            pass
        if self.corriendo_instalada:
            # El .exe no puede borrarse a sí mismo mientras corre: lo borra un cmd oculto al cerrar. Reintenta
            # cada segundo durante 30 s («timeout» no sirve: sin consola falla y el rmdir corría de inmediato).
            padre = os.path.dirname(self.carpeta)
            # como texto, no lista: Python escaparía las comillas como \" y cmd no lo entiende
            subprocess.Popen(
                f'cmd.exe /c "for /l %i in (1,1,30) do (ping -n 2 127.0.0.1 >nul & '
                f'if exist "{self.carpeta}" rmdir /s /q "{self.carpeta}") & rmdir "{padre}" 2>nul"',
                creationflags=CREATE_NO_WINDOW, close_fds=True)  # con DETACHED_PROCESS (sin consola) no corría
        else:
            shutil.rmtree(self.carpeta, ignore_errors=True)
            try:
                os.rmdir(os.path.dirname(self.carpeta))  # solo si GigaTech quedó vacía
            except OSError:
                pass

    def desinstalar(self, detalle="", limpiar=None):
        """Pregunta y desinstala. `limpiar` (opcional) deja la app en orden antes de borrar.
        Devuelve True si se desinstaló: el llamador debe cerrar la app de inmediato."""
        from PySide6.QtWidgets import QMessageBox
        detalle = detalle or self.nota_desinstalar
        elegido = _caja(
            QMessageBox.Warning, f"Desinstalar {self.titulo}", f"¿Quitar {self.titulo} de esta PC?",
            (detalle + "\n\n" if detalle else "") +
            ("Se quitan el arranque con Windows, el acceso del menú Inicio y la configuración." if self.arranque
             else "Se quitan el acceso del menú Inicio y la configuración."),
            [("Desinstalar", QMessageBox.AcceptRole), ("Cancelar", QMessageBox.RejectRole)])
        if elegido != "Desinstalar":
            return False
        self.cerrar_otras()
        if limpiar:
            try:
                limpiar()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.quitar()
        except Exception as e:  # noqa: BLE001
            _caja(QMessageBox.Warning, f"Desinstalar {self.titulo}", "No se pudo quitar todo.", str(e),
                  [("Aceptar", QMessageBox.AcceptRole)])
        return True


INSTALACION = Instalacion(
    titulo="GigaWalls",
    exe="GigaWalls.exe",
    clave="GigaTechGigaWalls",
    valor_run="AnimeWalls",          # nombre histórico del valor de arranque: se conserva
    version="1.2.4",
    descripcion="Fondos de escritorio animados · GigaTech",
    datos=("settings.json",),
    acento="#7c5cff",
    conserva="Tus ajustes y tu biblioteca",
    modo="carpeta",                  # Release = instalador (instalador.py); la app instalada es una carpeta
    nota_desinstalar="Los videos de tu biblioteca (Videos\\GigaWalls) no se borran.",
    repo="WeTeEfe/GigaWalls",        # las copias instaladas se actualizan desde sus Releases
)
