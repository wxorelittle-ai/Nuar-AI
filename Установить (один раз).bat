@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   METR - ustanovka (vypolnite odin raz)
echo ============================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python ne nayden.
  echo     Ustanovite Python 3.11+ s https://python.org
  echo     Pri ustanovke otmette galochku "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)
echo Ustanavlivayu zavisimosti...
python -m pip install -r requirements.txt
echo.
echo Gotovo. Teper zapuskayte fayl:  "Запустить МЭТР.bat"
echo.
pause
