@echo off
cd /d "%~dp0"
chcp 65001 >nul

if exist "%~dp0WallCal-1.1.0.exe" (
  start "" "%~dp0WallCal-1.1.0.exe"
  exit /b 0
)
if exist "%~dp0WallCal-1.0.0.exe" (
  start "" "%~dp0WallCal-1.0.0.exe"
  exit /b 0
)
if exist "%~dp0dist\WallCal-1.1.0.exe" (
  start "" "%~dp0dist\WallCal-1.1.0.exe"
  exit /b 0
)
if exist "%~dp0dist\WallCal-1.0.0.exe" (
  start "" "%~dp0dist\WallCal-1.0.0.exe"
  exit /b 0
)
if exist "%~dp0dist\WallCal.exe" (
  start "" "%~dp0dist\WallCal.exe"
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

echo 没有找到 Python，也没有 WallCal 可执行文件。
echo 请安装 Python 3.10+，或到 GitHub Releases 下载 exe。
pause
