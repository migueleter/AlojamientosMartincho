@echo off
cd /d "%~dp0"
echo Iniciando servidor local en http://localhost:8000 ...
start /min cmd /c "python scripts\server.py"
timeout /t 1 /nobreak >nul
start "" "http://localhost:8000/index.html"
