@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Discord Badge Idler
set "APP=%~dp0discord_badge_idler.py"
set "ERRLOG=%~dp0last_error.txt"
set "PYEXE="

if not exist "%APP%" (
    echo [!] discord_badge_idler.py was not found next to this file.
    echo     Put start.bat and discord_badge_idler.py in the same folder.
    pause
    exit /b 1
)

call :find_python
if defined PYEXE goto run

echo.
echo  Python 3 with tkinter was not found on this PC.
echo  The app needs it, and it can be installed for you now.
echo  (The EXE version of the app does not need Python at all.)
echo.
choice /C YN /M "Install Python now"
if errorlevel 2 goto manual
call :install_python
call :find_python
if defined PYEXE goto run
goto manual

:run
echo Starting with %PYEXE%
"%PYEXE%" "%APP%" %* 2> "%ERRLOG%"
set "CODE=%errorlevel%"
if "%CODE%"=="0" (
    del "%ERRLOG%" >nul 2>nul
    exit /b 0
)
echo.
echo [!] The program stopped with an error (exit code %CODE%):
echo ------------------------------------------------------------
type "%ERRLOG%"
echo ------------------------------------------------------------
echo This message was also saved to last_error.txt in this folder.
pause
exit /b %CODE%

:manual
echo.
echo Please install Python 3 from https://www.python.org/downloads/
echo During setup, tick "Add python.exe to PATH" and keep "tcl/tk and IDLE" selected.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

rem ---------------------------------------------------------------
rem Find a working Python 3.8+ that has tkinter (sets PYEXE)
rem ---------------------------------------------------------------
:find_python
for /f "usebackq delims=" %%P in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do call :try_python "%%P"
if defined PYEXE exit /b 0
for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable)" 2^>nul`) do call :try_python "%%P"
if defined PYEXE exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :try_python "%%D\python.exe"
if defined PYEXE exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-3*") do call :try_python "%%D\python.exe"
if defined PYEXE exit /b 0
for /d %%D in ("%ProgramFiles%\Python3*") do call :try_python "%%D\python.exe"
exit /b 0

:try_python
if defined PYEXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYEXE=%~1"
exit /b 0

rem ---------------------------------------------------------------
rem Install Python with winget (included with Windows 10/11)
rem ---------------------------------------------------------------
:install_python
where winget >nul 2>nul
if errorlevel 1 (
    echo winget is not available on this PC.
    exit /b 1
)
echo Installing Python 3.13 with winget. This can take a few minutes...
winget install --exact --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
exit /b 0
