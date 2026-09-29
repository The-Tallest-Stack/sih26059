@echo off
title Antarctic DSS - Public share
REM Share the app with anyone via a temporary public Cloudflare link.
REM   share_demo.bat       production build (fast for visitors; rebuilds on every start)
REM   share_demo.bat dev   dev mode (your edits show up live; slower for visitors)

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo cloudflared is not installed. Install it once with:
    echo     winget install Cloudflare.cloudflared
    echo then close and reopen this window.
    pause
    exit /b 1
)

echo [1/3] Starting backend API on port 8000...
start "Antarctic DSS Backend" cmd /k "cd /d "%~dp0backend" && set PYTHONPATH=src && .\.venv\Scripts\uvicorn.exe antarctic_dss.api.app:app --host 127.0.0.1 --port 8000"

cd /d "%~dp0frontend"
if /i "%1"=="dev" (
    echo [2/3] Starting website in DEV mode on port 3000 ^(live edits^)...
    start "Antarctic DSS Frontend" cmd /k "npm run dev -- -p 3000"
) else (
    echo [2/3] Building website for production ^(about 1 minute^)...
    call npm run build
    if errorlevel 1 (
        echo Build FAILED - fix the errors above, or run: share_demo.bat dev
        pause
        exit /b 1
    )
    start "Antarctic DSS Frontend" cmd /k "npm start -- -p 3000"
)

echo Waiting for the website to start...
timeout /t 8 >nul

echo.
echo [3/3] Opening public tunnel. Look for the https://....trycloudflare.com link below
echo       and send it to your friends. Keep this window open; close it to stop sharing.
echo.
cloudflared tunnel --url http://localhost:3000
