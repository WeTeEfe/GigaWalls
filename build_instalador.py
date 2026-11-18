"""Arma el instalador de Release a partir de la app ya compilada en carpeta (PyInstaller --onedir).

  python build_instalador.py <carpeta_app> <icono.ico> <Nombre>
    -> instalador\\<Nombre>.exe  (un solo archivo: instalador.py + app.zip + icono + CHANGELOG.md)

El instalador solo necesita QtWidgets para sus cuadros: la receta descarta el resto de Qt (Quick, Qml, red,
traducciones, OpenGL por software...), que PyInstaller copiaría por defecto (~45 MB de más).
Idéntico en las apps de GigaTech.
"""
import os
import shutil
import subprocess
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))

RECETA = r'''# Generado por build_instalador.py: no editar a mano.
import re
QT_LIBS = {"Core", "Gui", "Widgets"}
PLUGINS = re.compile(r"^PySide6/plugins/(platforms/qwindows|styles/|imageformats/q(ico|png|svg)|iconengines/)")


def keep(entry):
    dest = entry[0].replace("\\", "/")
    m = re.match(r"^PySide6/Qt6(\w+)\.dll$", dest)
    if m:
        return m.group(1) in QT_LIBS
    if dest.startswith("PySide6/plugins/"):
        return bool(PLUGINS.match(dest))
    if dest.startswith(("PySide6/translations/", "PySide6/qml/", "PySide6/resources/")):
        return False
    low = dest.lower()
    return not any(x in low for x in ("opengl32sw", "d3dcompiler", "qtwebengine", "avcodec", "avformat",
                                       "avutil", "swresample", "swscale"))


a = Analysis([{script!r}], datas={datas!r}, excludes=["tkinter", "numpy", "PySide6.QtNetwork", "PySide6.QtQml",
             "PySide6.QtQuick", "PySide6.QtMultimedia"], noarchive=False)
a.binaries = [e for e in a.binaries if keep(e)]
a.datas = [e for e in a.datas if keep(e)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name={nombre!r}, console=False, upx=False,
          icon=[{icono!r}])
'''


def main(carpeta, icono, nombre):
    carpeta = os.path.abspath(carpeta)
    if not os.path.isfile(os.path.join(carpeta, f"{nombre}.exe")):
        sys.exit(f"No existe {nombre}.exe en {carpeta}: compila primero la app en carpeta.")
    trabajo = os.path.join(AQUI, "build_instalador")
    os.makedirs(trabajo, exist_ok=True)
    paquete = os.path.join(trabajo, "app.zip")
    print(f"Comprimiendo {carpeta} ...", flush=True)
    with zipfile.ZipFile(paquete, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for raiz, _, archivos in os.walk(carpeta):
            for a in archivos:
                ruta = os.path.join(raiz, a)
                z.write(ruta, os.path.relpath(ruta, carpeta))
    print(f"app.zip: {os.path.getsize(paquete) / 1e6:.1f} MB", flush=True)
    ico = os.path.join(trabajo, "app.ico")
    shutil.copy2(icono, ico)  # dentro va como app.ico (lo busca instalador.py)
    receta = os.path.join(trabajo, f"{nombre}_instalador.spec")
    with open(receta, "w", encoding="utf-8") as f:
        valores = {"script": os.path.join(AQUI, "instalador.py"), "nombre": nombre, "icono": ico,
                   "datas": [(paquete, "."), (ico, "."), (os.path.join(AQUI, "CHANGELOG.md"), ".")]}
        texto = RECETA
        for clave, valor in valores.items():
            texto = texto.replace("{" + clave + "!r}", repr(valor))
        f.write(texto)
    comando = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--distpath", os.path.join(AQUI, "instalador"), "--workpath", trabajo, receta]
    if subprocess.run(comando, cwd=AQUI).returncode:
        sys.exit("La compilación del instalador falló.")
    exe = os.path.join(AQUI, "instalador", f"{nombre}.exe")
    print(f"Listo: {exe} ({os.path.getsize(exe) / 1e6:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
