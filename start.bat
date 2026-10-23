@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 discord_badge_idler.py %*
) else (
    python discord_badge_idler.py %*
)
if errorlevel 1 (
    echo.
    echo [!] The program stopped with an error. Please read the message above.
    pause
)
