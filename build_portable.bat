@echo off
rem Genera la version portable de GigaWalls (copiala a cualquier PC con Windows, sin instalar nada).
rem   build_portable.bat            -> carpeta portable\GigaWalls\ (GigaWalls.exe + _internal), arranca rapido
rem   build_portable.bat onefile    -> un solo archivo portable\GigaWalls.exe (descomprime en %TEMP% al abrir)
rem Requiere: pip install pyinstaller
cd /d "%~dp0"

set MODE=--onedir
set WORK=build
if /i "%1"=="onefile" (
  set MODE=--onefile
  set WORK=build_onefile
)

python make_icon.py || exit /b 1

python -m PyInstaller --noconfirm --clean --windowed %MODE% ^
  --name GigaWalls ^
  --icon "%~dp0assets\gigawalls.ico" ^
  --add-data "%~dp0assets;assets" ^
  --add-data "%~dp0CHANGELOG.md;." ^
  --collect-binaries imageio_ffmpeg ^
  --exclude-module tkinter ^
  --distpath "%~dp0portable" ^
  --workpath "%~dp0%WORK%" ^
  --specpath "%~dp0%WORK%" ^
  "%~dp0main.py" || exit /b 1

echo.
echo Listo (%MODE%) en %~dp0portable
