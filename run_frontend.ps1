# Start Frontend Server (PowerShell)
Write-Host "Starting InfiSupport Frontend (Streamlit)..." -ForegroundColor Green
Write-Host "Frontend will open at http://localhost:8501" -ForegroundColor Cyan
$env:BACKEND_URL = "http://localhost:8001"
& .\venv\Scripts\Activate.ps1
streamlit run frontend.py
