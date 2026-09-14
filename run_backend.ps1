# Start Backend Server (PowerShell)
Write-Host "Starting InfiSupport Backend Server..." -ForegroundColor Green
if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) {
	Write-Host "Backend is already running at http://localhost:8001" -ForegroundColor Cyan
	exit 0
}
& .\.venv\Scripts\Activate.ps1
& .\.venv\Scripts\python.exe -m uvicorn ai_cus_backend:app --host 0.0.0.0 --port 8001
