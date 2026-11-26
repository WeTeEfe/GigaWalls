<p align="center">
  <img src="assets/gigawalls_256.png" width="128" alt="GigaWalls">
</p>

<h1 align="center">GigaWalls</h1>

<p align="center">
  Fondos de escritorio animados para Windows · <b>GigaTech</b><br>
  <a href="https://github.com/WeTeEfe/GigaWalls/releases/latest"><img alt="Última versión" src="https://img.shields.io/github/v/release/WeTeEfe/GigaWalls?label=versi%C3%B3n&color=7c5cff"></a>
  <img alt="Windows 10 y 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4">
</p>

GigaWalls pone videos como fondo de pantalla, detrás de los iconos del escritorio. Busca fondos animados en varios catálogos, los descarga a tu biblioteca y los reproduce en todos tus monitores, gastando lo menos posible de la PC.

## Descargar

1. Baja **[GigaWalls.exe](https://github.com/WeTeEfe/GigaWalls/releases/latest/download/GigaWalls.exe)** (la versión más nueva).
2. Ábrelo y elige **Instalar**. No pide administrador, queda en el menú Inicio y arranca con Windows.

Después **se actualiza solo**: revisa al abrir y cada 6 horas, te avisa cuando hay una versión nueva y se instala conservando tus ajustes y tu biblioteca. También puedes revisar a mano con **Buscar actualizaciones ahora**, en el ícono junto al reloj.

Para desinstalarlo, usa *Aplicaciones instaladas* de Windows o el ícono junto al reloj. Los videos de tu biblioteca no se borran.

## Qué hace

- **Buscar y descargar fondos** de MoeWalls, DesktopHut, MotionBGS y LiveWallpapers4Free, con vista previa. Puedes buscar en español: la búsqueda se traduce sola.
- **Tu biblioteca** en `Videos\GigaWalls`. También importa tus propios videos, marca favoritos y limpia duplicados.
- **Varios monitores**: el video se ve en todas las pantallas o solo en la principal, y se ajusta solo cuando conectas, apagas o reacomodas monitores.
- **Rotación automática** entre tus favoritos (o toda la biblioteca), o pasa al **siguiente fondo** cuando quieras.
- **Reflejar** el video a lo ancho o a lo alto antes de descargarlo.
- **Ahorra recursos**:
  - *Pausar si lo tapan*: deja de reproducir en los monitores tapados por una ventana maximizada, y se pausa del todo con juegos o videos a pantalla completa.
  - *Modo ahorro*: guarda los videos en 720p y 24 fps.
  - *Optimizar*: recomprime el video seleccionado para que use menos GPU.
- **Novedades**: al actualizarse te muestra lo que cambió. El historial completo está en [CHANGELOG.md](CHANGELOG.md).

## Desde el código

Requiere Windows y Python 3.12 o más nuevo.

```bash
pip install PySide6 requests beautifulsoup4 opencv-python numpy imageio-ffmpeg pyinstaller
python main.py
```

| Comando | Para qué |
|---|---|
| `python main.py --smoketest informe.txt` | Prueba completa: catálogos, descargas, biblioteca, reproducción y actualizaciones |
| `build_portable.bat` | Compila la app (carpeta) y el instalador de un solo archivo |
| `python release.py` | Publica una versión: sube el número, prueba el código y el .exe, compila, guarda en git y la sube a GitHub Releases |

Antes de publicar, `release.py` exige que [CHANGELOG.md](CHANGELOG.md) tenga la sección de la versión nueva. Esos cambios son los que ven los usuarios al actualizar.

### Archivos principales

| Archivo | Qué contiene |
|---|---|
| `main.py` | Ventana, bandeja, biblioteca y ajustes |
| `desktop.py` | El fondo detrás de los iconos, varios monitores y pausa al taparlo |
| `moewalls.py`, `desktophut.py`, `motionbgs.py`, `livewallpapers4free.py` | Catálogos de fondos |
| `optimize.py` | Recompresión y reflejado con ffmpeg |
| `instalacion.py`, `instalador.py` | Instalar, actualizar desde GitHub y desinstalar |
| `release.py` | Publicación con pruebas |

---

<p align="center">© GigaTech</p>
