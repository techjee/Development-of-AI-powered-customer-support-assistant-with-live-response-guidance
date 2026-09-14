# InfiSupport - Startup Guide

## Quick Start (Windows PowerShell)

### Option 1: Run Backend Only
```powershell
.\run_backend.ps1
```
Backend will be available at: http://localhost:8001

### Option 2: Run Both Backend & Frontend (Recommended)

**Terminal 1 - Backend:**
```powershell
.\run_backend.ps1
```

**Terminal 2 - Frontend:**
```powershell
.\run_frontend.ps1
```

Frontend will open at: http://localhost:8501

### Login Accounts

Initialize database-backed users with passwords supplied through your local environment:

```powershell
$env:ADMIN_USERNAME="admin@infosys.com"
$env:ADMIN_INITIAL_PASSWORD="choose-a-password"
$env:AGENT_USERNAME="agent@infosys.com"
$env:AGENT_INITIAL_PASSWORD="choose-a-password"
.\.venv\Scripts\python.exe initialize_users.py
```

Set the following variables in `.env` before starting the backend:

```text
AUTH_SECRET=replace-with-a-long-random-secret
AUTH_EMAIL_DOMAIN=infosys.com
AGENT_USERNAME=agent@infosys.com
AGENT_INITIAL_PASSWORD=choose-a-password
ADMIN_USERNAME=admin@infosys.com
ADMIN_INITIAL_PASSWORD=choose-a-password
```

Human agents are sent to the support copilot workspace. Administrators are sent to the protected overview dashboard. Backend ticket and case APIs require a valid login token, and vector case ingestion is admin-only.

## Architecture

```
InfiSupport CBR System
├── Backend (FastAPI)
│   ├── ai_cus_backend.py       → Main API server (Gemini-powered)
│   ├── vector_db.py            → Vector similarity search
│   └── database.py              → PostgreSQL persistence and schema setup
│
├── Frontend (Streamlit)
│   └── frontend.py             → UI for agent coaching
│
└── Environment
    ├── .env                    → Gemini API credentials
    ├── requirements.txt        → Python dependencies
    └── venv/                   → Virtual environment
```

## API Endpoints

- **POST /api/tickets/process-text** - Process text-only customer complaint
- **POST /api/tickets/process-multimodal** - Process complaint with image
- **POST /api/cases/add** - Add new case to vector database
- **GET /health** - Health check

## Troubleshooting

### Issue: Uvicorn reload errors on Windows
**Solution:** Use `run_backend.ps1` - it runs without `--reload` flag which avoids multiprocessing issues on Windows.

### Issue: Port 8000 already in use
```powershell
# Kill the process using port 8000
$process = Get-NetTCPConnection -LocalPort 8000 | Select-Object -ExpandProperty OwningProcess
Stop-Process -Id $process -Force

# Or run on different port
uvicorn ai_cus_backend:app --port 8001
```

### Issue: Frontend can't connect to backend
- Make sure backend is running on http://localhost:8001
- Check BACKEND_URL in frontend.py matches your backend address

## Environment Variables (.env)

```
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-1.5-flash
```

Get your Gemini API key from: https://aistudio.google.com/app/apikey

## Virtual Environment

Activate:
```powershell
.\venv\Scripts\Activate.ps1
```

Deactivate:
```powershell
deactivate
```

Install dependencies:
```powershell
pip install -r requirements.txt
```

---

**System Status:** ✓ Gemini API Integrated | ✓ All Dependencies Installed
