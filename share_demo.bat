@echo off
title Antarctic DSS - Public share
REM Share the app with anyone via a temporary public link.
REM   share_demo.bat                  production build; ngrok fixed link if set up (ngrok_domain.txt),
REM                                   otherwise a Pinggy tunnel (new link every 60 minutes)
REM   share_demo.bat dev              dev mode: your edits show up live (slower for visitors)
REM   share_demo.bat pinggy           force Pinggy even if ngrok is set up
REM   share_demo.bat cloudflare       use a Cloudflare tunnel instead (needs outbound port 7844)
REM   share_demo.bat dev cloudflare   both

set MODE=prod
set TUNNEL=pinggy
set NGROK_DOMAIN=
REM ngrok_domain.txt (git-ignored) holds your free static domain, e.g. my-app.ngrok-free.app
if exist "%~dp0ngrok_domain.txt" set /p NGROK_DOMAIN=<"%~dp0ngrok_domain.txt"
if defined NGROK_DOMAIN (
    where ngrok >nul 2>nul
    if not errorlevel 1 set TUNNEL=ngrok
)
for %%A in (%*) do (
    if /i "%%A"=="dev" set MODE=dev
    if /i "%%A"=="cloudflare" set TUNNEL=cloudflare
    if /i "%%A"=="pinggy" set TUNNEL=pinggy
)
echo Tunnel: %TUNNEL%

if "%TUNNEL%"=="cloudflare" (
    where cloudflared >nul 2>nul
    if errorlevel 1 (
        echo cloudflared is not installed. Install it with: winget install Cloudflare.cloudflared
        pause
        exit /b 1
    )
) else (
    where ssh >nul 2>nul
    if errorlevel 1 (
        echo ssh is not available. Enable "OpenSSH Client" in Windows Settings ^> Optional features.
        pause
        exit /b 1
    )
)

echo [1/3] Starting backend API on port 8000...
start "Antarctic DSS Backend" cmd /k "cd /d "%~dp0backend" && set PYTHONPATH=src && .\.venv\Scripts\uvicorn.exe antarctic_dss.api.app:app --host 127.0.0.1 --port 8000"

cd /d "%~dp0frontend"
if "%MODE%"=="dev" (
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
echo [3/3] Opening public tunnel. Send the https:// link shown below to your friends.
echo       Keep this window open; close it to stop sharing.
echo.
if "%TUNNEL%"=="cloudflare" (
    cloudflared tunnel --url http://localhost:3000
    exit /b
)
if "%TUNNEL%"=="ngrok" (
    echo Your permanent link: https://%NGROK_DOMAIN%
    echo.
    ngrok http --domain=%NGROK_DOMAIN% 3000
    exit /b
)

:pinggy
REM Pinggy runs over SSH on port 443 (rarely blocked). Free links expire after 60 minutes;
REM this loop reconnects automatically - with a NEW link each time.
ssh -p 443 -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -T -R0:localhost:3000 a.pinggy.io
echo.
echo Tunnel ended (free links last 60 minutes). Reconnecting with a NEW link in 5 seconds...
echo Close this window to stop sharing.
timeout /t 5 >nul
goto pinggy
