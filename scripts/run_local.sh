#!/usr/bin/env bash
# Run backend (SQLite) + frontend dev server without Docker. Needs Python 3.11+, Node 18+.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/init_env.py
cd backend
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000 &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd ../frontend
npm install --no-audit --no-fund
npm run dev
