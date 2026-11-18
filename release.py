"""Publica GigaWalls en Desktop\\Release solo si pasa todas las pruebas.

  1. Sube la versión en instalacion.py (1.0.5 -> 1.0.6, o la que se indique) para que el instalador ofrezca
     «Actualizar». Antes exige que CHANGELOG.md tenga la sección de esa versión (lo que verá el usuario en «Novedades»).
  2. Prueba completa desde el código (main.py --smoketest).
  3. Compila la app en carpeta y el instalador que la lleva dentro (build_portable.bat).
  4. Repite la prueba con la app ya compilada (detecta lo que falte en el empaquetado) y revisa el paquete
     del instalador (--probar).
  5. Copia el instalador a Desktop\\Release y guarda la versión en git (commit + etiqueta).

Si algo falla se detiene, deja la versión como estaba y no toca Release.
Uso: python release.py [versión]   (o doble clic en release.bat)
"""
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
INSTALACION = os.path.join(AQUI, "instalacion.py")
EXE = os.path.join(AQUI, "portable", "GigaWalls", "GigaWalls.exe")       # la app (carpeta)
INSTALADOR = os.path.join(AQUI, "instalador", "GigaWalls.exe")          # lo que va a Release
RELEASE = os.path.join(os.path.expanduser("~"), "Desktop", "Release", "GigaWalls.exe")
PATRON = re.compile(r'(\n    version=")(\d+(?:\.\d+)*)(",)')


def paso(texto):
    print(f"\n=== {texto} ===", flush=True)


def leer_version():
    with open(INSTALACION, encoding="utf-8") as f:
        texto = f.read()
    m = PATRON.search(texto)
    if not m:
        sys.exit("No encontré version=\"...\" en instalacion.py")
    return texto, m.group(2)


def escribir_version(texto, version):
    with open(INSTALACION, "w", encoding="utf-8", newline="") as f:
        f.write(PATRON.sub(lambda m: m.group(1) + version + m.group(3), texto, count=1))


def prueba(comando, informe, nombre):
    if os.path.exists(informe):
        os.remove(informe)
    codigo = subprocess.run(comando, cwd=AQUI).returncode
    texto = open(informe, encoding="utf-8").read() if os.path.exists(informe) else "(no generó informe)\n"
    print(texto, end="")
    if codigo != 0:
        raise RuntimeError(f"la prueba {nombre} falló (código {codigo})")


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=AQUI, check=check, capture_output=True, text=True)


def main():
    original, anterior = leer_version()
    partes = anterior.split(".")
    partes[-1] = str(int(partes[-1]) + 1)
    nueva = sys.argv[1] if len(sys.argv) > 1 else ".".join(partes)
    if not re.fullmatch(r"\d+\.\d+\.\d+", nueva) or \
            tuple(map(int, nueva.split("."))) <= tuple(map(int, anterior.split("."))):
        sys.exit(f"Versión no válida: {nueva} (debe ser mayor que {anterior}).")
    with open(os.path.join(AQUI, "CHANGELOG.md"), encoding="utf-8") as f:
        if not re.search(rf"^##\s+{re.escape(nueva)}\b", f.read(), re.M):
            sys.exit(f"Falta la sección «## {nueva} — fecha» en CHANGELOG.md (lo que cambió en esta versión). "
                     "Agrégala y vuelve a correr release.")
    paso(f"Versión {anterior} -> {nueva}")
    escribir_version(original, nueva)
    try:
        paso("Prueba desde el código")
        prueba([sys.executable, "main.py", "--smoketest", os.path.join(AQUI, "smoketest_codigo.txt")],
               os.path.join(AQUI, "smoketest_codigo.txt"), "desde el código")

        paso("Compilando la app y el instalador (tarda unos minutos)")
        if subprocess.run(["cmd", "/c", os.path.join(AQUI, "build_portable.bat")], cwd=AQUI).returncode:
            raise RuntimeError("la compilación falló")

        paso("Prueba de la app compilada")
        prueba([EXE, "--smoketest", os.path.join(AQUI, "smoketest_exe.txt")],
               os.path.join(AQUI, "smoketest_exe.txt"), "de la app compilada")

        paso("Prueba del instalador")
        prueba([INSTALADOR, "--probar", os.path.join(AQUI, "smoketest_instalador.txt")],
               os.path.join(AQUI, "smoketest_instalador.txt"), "del instalador")
    except Exception as e:  # noqa: BLE001
        escribir_version(original, anterior)  # no quemar un número de versión que no se publicó
        print(f"\nNO SE PUBLICÓ: {e}. Release quedó como estaba y la versión volvió a {anterior}.")
        return 1

    paso("Copiando a Release")
    os.makedirs(os.path.dirname(RELEASE), exist_ok=True)
    shutil.copy2(INSTALADOR, RELEASE)
    print(f"{RELEASE} ({os.path.getsize(RELEASE) / 1e6:.0f} MB)")

    paso("Guardando en git")
    git("add", "-A")
    if git("diff", "--cached", "--quiet", check=False).returncode:
        coautor = os.environ.get("RELEASE_COAUTOR")  # línea Co-Authored-By opcional
        git("commit", "-q", "-m", f"GigaWalls {nueva}" + (f"\n\n{coautor}" if coautor else ""))
    git("tag", "-f", f"v{nueva}")
    print(git("log", "--oneline", "-1").stdout.strip())

    print(f"\nLISTO: GigaWalls {nueva} publicado y probado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
