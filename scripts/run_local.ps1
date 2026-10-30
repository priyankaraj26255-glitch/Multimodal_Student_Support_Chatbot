# Windows PowerShell: run backend (SQLite) + frontend without Docker. Needs Python 3.11+ and Node 18+.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python scripts/init_env.py
Set-Location backend
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q -r requirements.txt
.\.venv\Scripts\alembic upgrade head
$back = Start-Process -PassThru -NoNewWindow .\.venv\Scripts\uvicorn -ArgumentList "app.main:app","--reload","--port","8000"
try {
  Set-Location ..\frontend
  npm install --no-audit --no-fund
  npm run dev
} finally { Stop-Process -Id $back.Id -ErrorAction SilentlyContinue }
