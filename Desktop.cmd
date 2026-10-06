@echo off
setlocal
cd /d "%~dp0"
if exist dist\GTD\GTD.exe (
 start "" dist\GTD\GTD.exe
 exit /b 0
)
if not exist .venv-desktop\Scripts\pythonw.exe (
 echo Run "Build Desktop.cmd" first.
 exit /b 1
)
start "" .venv-desktop\Scripts\pythonw.exe desktop.py
