@echo off
REM package.bat — one-click Windows build of ZaraSetup.exe.
REM
REM Double-click this file, or run it from a terminal. It runs the Python build
REM script with the same interpreter that is on PATH, so make sure that is the
REM one you ran `python setup.py` with.
REM
REM Usage:
REM   package.bat                 full build
REM   package.bat --clean         wipe build\ and dist\ first
REM   package.bat --skip-browsers skip the Playwright browser download
REM   package.bat --skip-installer  stop after dist\ZaraAI (no installer)
REM
REM Any arguments are passed straight through to packaging\build.py.

setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo   Python was not found on PATH.
    echo   Install Python 3.11 or newer from https://www.python.org/downloads/
    echo   and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

echo.
echo ====================================================================
echo   Building Zara AI
echo ====================================================================

python packaging\build.py %*

set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (
    echo   Build finished. Look in dist\ for ZaraAI\ and ZaraSetup.exe.
) else (
    echo   Build failed with exit code %RC%. Scroll up for the error.
)
echo.
pause
exit /b %RC%
