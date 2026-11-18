@echo off
rem Compila GigaWalls:
rem   1) la app en carpeta   -> portable\GigaWalls\ (GigaWalls.exe + _internal), es lo que se instala y abre rapido
rem   2) el instalador       -> instalador\GigaWalls.exe (un solo archivo con la carpeta comprimida dentro)
rem El de Release es el instalador (lo copia release.py). Requiere: pip install pyinstaller
cd /d "%~dp0"

python make_icon.py || exit /b 1

python -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name GigaWalls ^
  --icon "%~dp0assets\gigawalls.ico" ^
  --add-data "%~dp0assets;assets" ^
  --add-data "%~dp0CHANGELOG.md;." ^
  --collect-binaries imageio_ffmpeg ^
  --exclude-module tkinter ^
  --distpath "%~dp0portable" ^
  --workpath "%~dp0build" ^
  --specpath "%~dp0build" ^
  "%~dp0main.py" || exit /b 1

python build_instalador.py "%~dp0portable\GigaWalls" "%~dp0assets\gigawalls.ico" GigaWalls || exit /b 1

echo.
echo Listo: %~dp0instalador\GigaWalls.exe
