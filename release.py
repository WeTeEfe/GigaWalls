"""Publica GigaWalls en Desktop\\Release solo si pasa todas las pruebas.

  1. Sube la versión en instalacion.py (1.0.5 -> 1.0.6) para que el exe ofrezca «Actualizar».
  2. Prueba completa desde el código (main.py --smoketest).
  3. Compila el .exe de un solo archivo (build_portable.bat onefile).
  4. Repite la prueba con el .exe ya compilado (detecta lo que falte en el empaquetado).
  5. Copia el .exe a Desktop\\Release y guarda la versión en git (commit + etiqueta).

Si algo falla se detiene, deja la versión como estaba y no toca Release.
Uso: python release.py   (o doble clic en release.bat)
"""
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
INSTALACION = os.path.join(AQUI, "instalacion.py")
EXE = os.path.join(AQUI, "portable", "GigaWalls.exe")
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
    nueva = ".".join(partes)
    paso(f"Versión {anterior} -> {nueva}")
    escribir_version(original, nueva)
    try:
        paso("Prueba desde el código")
        prueba([sys.executable, "main.py", "--smoketest", os.path.join(AQUI, "smoketest_codigo.txt")],
               os.path.join(AQUI, "smoketest_codigo.txt"), "desde el código")

        paso("Compilando el .exe (tarda unos minutos)")
        if subprocess.run(["cmd", "/c", os.path.join(AQUI, "build_portable.bat"), "onefile"], cwd=AQUI).returncode:
            raise RuntimeError("la compilación falló")

        paso("Prueba del .exe compilado")
        prueba([EXE, "--smoketest", os.path.join(AQUI, "smoketest_exe.txt")],
               os.path.join(AQUI, "smoketest_exe.txt"), "del .exe")
    except Exception as e:  # noqa: BLE001
        escribir_version(original, anterior)  # no quemar un número de versión que no se publicó
        print(f"\nNO SE PUBLICÓ: {e}. Release quedó como estaba y la versión volvió a {anterior}.")
        return 1

    paso("Copiando a Release")
    os.makedirs(os.path.dirname(RELEASE), exist_ok=True)
    shutil.copy2(EXE, RELEASE)
    print(RELEASE)

    paso("Guardando en git")
    git("add", "-A")
    if git("diff", "--cached", "--quiet", check=False).returncode:
        git("commit", "-q", "-m", f"GigaWalls {nueva}")
    git("tag", "-f", f"v{nueva}")
    print(git("log", "--oneline", "-1").stdout.strip())

    print(f"\nLISTO: GigaWalls {nueva} publicado y probado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
