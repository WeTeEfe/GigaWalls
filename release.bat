@echo off
rem Publica GigaWalls en Desktop\Release solo si pasa todas las pruebas (ver release.py).
cd /d "%~dp0"
python release.py
pause
