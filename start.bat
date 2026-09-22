@echo off
cd /d "%~dp0"
chcp 65001 >nul
set /p WALLCAL_VERSION=<"%~dp0VERSION"
if exist "%~dp0WallCal-%WALLCAL_VERSION%.exe" (
  start "" "%~dp0WallCal-%WALLCAL_VERSION%.exe"
  exit /b 0
)
if exist "%~dp0dist\WallCal-%WALLCAL_VERSION%.exe" (
  start "" "%~dp0dist\WallCal-%WALLCAL_VERSION%.exe"
  exit /b 0
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
  exit /b 0
)
where py >nul 2>&1
if %errorlevel%==0 (
  start "" py -3 "%~dp0main.py"
  exit /b 0
)
where python >nul 2>&1
if %errorlevel%==0 (
  start "" python "%~dp0main.py"
  exit /b 0
)
echo 没有找到 Python 或当前版本的 WallCal EXE。
echo 请安装 Python 3.10+ 并安装 requirements.txt，或下载绿色软件。
pause
