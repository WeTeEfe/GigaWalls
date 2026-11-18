"""Instalador del .exe de Release (modo carpeta de instalacion.py).

Es un PyInstaller --onefile pequeño: solo trae PySide6 (para los cuadros), instalacion.py y, como datos,
app.zip (la app compilada con --onedir), app.ico y CHANGELOG.md. Al abrirlo muestra el menú inicial
(instalar / actualizar / abrir / reinstalar / desinstalar), reemplaza la carpeta del programa en
%LocalAppData%\\GigaTech\\<App> y abre la copia instalada, que arranca rápido porque no descomprime nada.

  --instalar      instala sin preguntar (para scripts)
  --desinstalar   pregunta y desinstala
  --probar INF    revisa que el paquete esté completo y escribe el resultado en INF (lo usa release)

Idéntico en las apps de GigaTech: la configuración está en INSTALACION (instalacion.py).
"""
import ctypes
import os
import sys

from instalacion import INSTALACION


def probar(informe):
    import zipfile
    lineas, ok = [], True
    try:
        with zipfile.ZipFile(INSTALACION._zip or "") as z:
            nombres = z.namelist()
            malo = z.testzip()
        tiene_exe = INSTALACION.exe_nombre in nombres
        tiene_internal = any(n.startswith("_internal/") for n in nombres)
        ok = tiene_exe and tiene_internal and malo is None
        lineas.append(f"{'OK    ' if ok else 'FALLA '} app.zip: {len(nombres)} archivos, exe={tiene_exe}, "
                      f"_internal={tiene_internal}, dañado={malo}")
    except Exception as e:  # noqa: BLE001
        ok = False
        lineas.append(f"FALLA  app.zip: {type(e).__name__}: {e}")
    lineas.append(f"OK     versión: {INSTALACION.version}")
    with open(informe, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + f"\nRESULTADO: {'TODO OK' if ok else 'HAY FALLOS'}\n")
    return 0 if ok else 1


def main():
    if "--probar" in sys.argv:
        return probar(sys.argv[sys.argv.index("--probar") + 1])
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"GigaTech.{INSTALACION.titulo}.Instalador")
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName(INSTALACION.titulo)
    app.setWindowIcon(QIcon(os.path.join(getattr(sys, "_MEIPASS", ""), "app.ico")))
    if "--desinstalar" in sys.argv:
        INSTALACION.desinstalar()
    else:
        INSTALACION.ofrecer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
