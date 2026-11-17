"""Instalar / actualizar / desinstalar en la PC actual, solo para el usuario (sin administrador).

El .exe sigue siendo portable: al abrirlo desde un USB ofrece instalarse (o actualizar la copia
instalada) y, si se prefiere, "Solo abrir". La copia instalada vive en
%LocalAppData%\\GigaTech\\<Programa>, queda en el menú Inicio, en «Aplicaciones instaladas» de Windows
y puede arrancar con Windows. Se desinstala desde Windows o desde el ícono junto al reloj.

Este archivo es idéntico en GigaWalls y Grabador de pantalla: lo único que cambia es la
configuración al final (INSTALACION = Instalacion(...)).
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


def _caja(icono, titulo, texto, detalle, botones):
    """Cuadro de mensaje con botones personalizados. Devuelve el texto del botón elegido."""
    from PySide6.QtWidgets import QMessageBox
    m = QMessageBox()
    m.setIcon(icono)
    m.setWindowTitle(titulo)
    m.setText(texto)
    m.setInformativeText(detalle)
    primero = None
    for i, (t, rol) in enumerate(botones):
        b = m.addButton(t, rol)
        if i == 0:
            primero = b
    m.setDefaultButton(primero)
    m.exec()
    return m.clickedButton().text() if m.clickedButton() else ""


class Instalacion:
    def __init__(self, titulo, exe, clave, valor_run, version, arg_inicio="--minimized",
                 descripcion="", datos=()):
        self.titulo = titulo            # nombre visible: «GigaWalls»
        self.exe_nombre = exe           # «GigaWalls.exe»
        self.clave = clave              # subclave en «Aplicaciones instaladas»
        self.valor_run = valor_run      # nombre del valor de arranque con Windows
        self.version = version          # «1.0.0»
        self.arg_inicio = arg_inicio    # argumentos al arrancar con Windows
        self.descripcion = descripcion
        self.datos = tuple(datos)       # archivos de ajustes junto al .exe que se llevan al instalar

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
    def cerrar_otras(self):
        """Cierra las copias instaladas que estén abiertas (no se puede reemplazar un .exe en uso)."""
        yo = f"{os.getpid()},{os.getppid()}"  # el proceso y su lanzador (onefile)
        _ps(f"Get-Process | Where-Object {{ $_.Path -eq '{_q(self.exe)}' -and $_.Id -notin @({yo}) }}"
            " | Stop-Process -Force -ErrorAction SilentlyContinue")
        time.sleep(0.8)

    def instalar(self):
        origen = self.ruta_actual
        self.cerrar_otras()
        os.makedirs(self.carpeta, exist_ok=True)
        shutil.copy2(origen, self.exe)
        for nombre in self.datos:  # lleva los ajustes del .exe portable, sin pisar los ya instalados
            src, dst = os.path.join(os.path.dirname(origen), nombre), os.path.join(self.carpeta, nombre)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
        _ps("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
            "$s.TargetPath='{exe}';$s.WorkingDirectory='{dir}';$s.Description='{desc}';$s.Save()".format(
                lnk=_q(self._acceso), exe=_q(self.exe), dir=_q(self.carpeta),
                desc=_q(self.descripcion or self.titulo)))
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
            num("EstimatedSize", int(os.path.getsize(self.exe) / 1024))

    def abrir_instalada(self):
        """Lanza la copia instalada. Devuelve True: esta instancia debe cerrarse."""
        env = {k: v for k, v in os.environ.items() if k != "_MEIPASS2" and not k.startswith("_PYI")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # que no reutilice la carpeta temporal de esta
        args = [a for a in sys.argv[1:] if a != "--instalar"]
        subprocess.Popen([self.exe, *args], env=env, cwd=self.carpeta, close_fds=True,
                         creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)
        return True

    def ofrecer(self, detalle_desinstalar=""):
        """Al abrir el .exe publicado fuera de su carpeta de instalación muestra el estado de la PC y
        ofrece, según el caso: instalar, actualizar, reinstalar, desinstalar o abrir la copia instalada.
        Devuelve True si esta instancia debe cerrarse (se abrió la instalada o se desinstaló)."""
        if not self.publicada or self.corriendo_instalada:
            return False
        from PySide6.QtWidgets import QMessageBox
        instalada = self.version_instalada
        nueva = _version(self.version)
        txt_inst = ".".join(map(str, instalada)) if instalada is not None else ""
        if "--instalar" in sys.argv:  # instalación por script, sin preguntar
            if instalada is not None and instalada >= nueva:
                return self.abrir_instalada()
        else:
            info = ("Se instala solo para este usuario (no pide administrador), arranca con Windows y queda "
                    "en el menú Inicio. También se puede desinstalar desde Windows (Aplicaciones) o desde su "
                    "ícono junto al reloj.")
            if instalada is None:
                titulo, texto = f"Instalar {self.titulo}", f"¿Instalar {self.titulo} {self.version} en esta PC?"
                botones = [("Instalar", QMessageBox.AcceptRole), ("Solo abrir", QMessageBox.RejectRole)]
            elif instalada < nueva:
                titulo = f"Actualizar {self.titulo}"
                texto = (f"Hay una versión anterior instalada ({txt_inst}).\n"
                         f"¿Actualizar a la {self.version}?")
                botones = [("Actualizar", QMessageBox.AcceptRole), ("Desinstalar", QMessageBox.DestructiveRole)]
            elif instalada == nueva:
                titulo = self.titulo
                texto = f"✔ Ya tienes la versión más actual instalada ({txt_inst})."
                info = "Puedes abrirla, reinstalarla (si algo falla) o quitarla de esta PC."
                botones = [("Abrir", QMessageBox.AcceptRole), ("Reinstalar", QMessageBox.ActionRole),
                           ("Desinstalar", QMessageBox.DestructiveRole)]
            else:
                titulo = self.titulo
                texto = (f"La versión instalada ({txt_inst}) es más nueva que este archivo ({self.version}).\n"
                         "Ya tienes la versión más actual.")
                info = "Se abrirá la versión instalada. Este archivo es antiguo y se puede borrar."
                botones = [("Abrir", QMessageBox.AcceptRole), ("Desinstalar", QMessageBox.DestructiveRole)]
            elegido = _caja(QMessageBox.Question if instalada is None or instalada < nueva
                            else QMessageBox.Information, titulo, texto, info, botones)
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
            _caja(QMessageBox.Warning, f"Instalar {self.titulo}", "No se pudo instalar. Se abre sin instalar.",
                  str(e), [("Aceptar", QMessageBox.AcceptRole)])
            return False
        return self.abrir_instalada()

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
            # El .exe no puede borrarse a sí mismo mientras corre: lo borra un cmd oculto al cerrar.
            padre = os.path.dirname(self.carpeta)
            subprocess.Popen(
                ["cmd.exe", "/c", f'timeout /t 3 /nobreak >nul & rmdir /s /q "{self.carpeta}" & rmdir "{padre}"'],
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True)
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
        elegido = _caja(
            QMessageBox.Warning, f"Desinstalar {self.titulo}", f"¿Quitar {self.titulo} de esta PC?",
            (detalle + "\n\n" if detalle else "") +
            "Se quitan el arranque con Windows, el acceso del menú Inicio y la configuración.",
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
    version="1.0.5",
    descripcion="Fondos de escritorio animados · GigaTech",
    datos=("settings.json",),
)
