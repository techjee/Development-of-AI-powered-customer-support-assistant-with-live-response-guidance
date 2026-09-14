@echo off
REM Start Backend without --reload to avoid Windows multiprocessing issues
echo Starting InfiSupport Backend Server...
netstat -ano | findstr ":8001 .*LISTENING" >nul
if %errorlevel% equ 0 (
	echo Backend is already running at http://localhost:8001
	exit /b 0
)
call venv\Scripts\activate.bat
venv\Scripts\python.exe -m uvicorn ai_cus_backend:app --host 0.0.0.0 --port 8001
pause
