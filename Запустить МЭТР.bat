@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   METR zapushchen.
echo   Otkroytsya v brauzere: http://localhost:8000
echo.
echo   Nastroyki i API-klyuchi:  http://localhost:8000/settings
echo.
echo   Chtoby ostanovit - zakroyte eto okno.
echo ============================================
echo.
start "" http://localhost:8000
python -m web.app
pause
