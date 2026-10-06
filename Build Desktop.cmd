@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
py -3.13 -m venv .venv-desktop
if errorlevel 1 goto failed
.venv-desktop\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
.venv-desktop\Scripts\python.exe scripts\prepare_desktop_tools.py
if errorlevel 1 goto failed
.venv-desktop\Scripts\python.exe scripts\build_desktop.py
if errorlevel 1 goto failed
echo Build complete. Run dist\GTD\GTD.exe.
echo ZIP and SHA256 are available in dist.
pause
exit /b 0
:failed
echo Build failed. See the error above. Source builds require Python 3.13 x64 and internet access.
echo Packaged builds from GitHub Actions do not require Python.
pause
exit /b 1
