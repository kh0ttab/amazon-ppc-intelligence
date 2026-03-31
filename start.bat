@echo off
echo.
echo   Amazon PPC Intelligence v2.0
echo   ================================
echo.

echo   [1/3] Installing backend...
cd /d "%~dp0backend"
pip install -r requirements.txt -q 2>nul

echo   [2/3] Starting backend on :8000...
start /b cmd /c "cd /d "%~dp0backend" && uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level warning"

echo   [3/3] Starting frontend on :5173...
cd /d "%~dp0frontend"
call npm install --silent 2>nul
start /b cmd /c "cd /d "%~dp0frontend" && npm run dev"

timeout /t 4 /nobreak >nul
echo.
echo   Ready! Opening http://localhost:5173
echo   Close this window to stop.
echo.
start http://localhost:5173
pause
