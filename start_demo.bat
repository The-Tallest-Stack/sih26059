@echo off
echo ===================================================
echo Starting Antarctic Voyage Decision Support System
echo ===================================================

echo [1/2] Starting Python FastAPI Backend on Port 8000...
start "Antarctic DSS Backend" cmd /k "cd backend && set PYTHONPATH=src && .\.venv\Scripts\uvicorn.exe antarctic_dss.api.app:app --host 0.0.0.0 --port 8000"

echo [2/2] Starting Next.js Frontend on Port 3000...
start "Antarctic DSS Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both servers are starting up!
echo The frontend will open in your browser shortly...
timeout /t 5
start http://localhost:3000
