@echo off
rem ===========================================================
rem  Merge the upstream release into this copy, keeping your own
rem  changes. Double-click this file.
rem
rem  ASCII-only on purpose: .bat files are read using the console
rem  code page, so non-ASCII text breaks the parser.
rem ===========================================================
cd /d "%~dp0"

set "PYEXE="
if exist "%~dp0python\python.exe" set "PYEXE=%~dp0python\python.exe"
if defined PYEXE goto run

python --version >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto run

py --version >nul 2>nul
if not errorlevel 1 set "PYEXE=py"
if defined PYEXE goto run

echo [ERROR] No usable Python found.
echo         Install Python 3.9+ from https://www.python.org/downloads/
echo         (tick "Add python.exe to PATH" during setup)
pause
exit /b 1

:run
"%PYEXE%" "%~dp0update-from-upstream.py"
