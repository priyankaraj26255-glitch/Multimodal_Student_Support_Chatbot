.PHONY: setup up down logs test backend frontend

setup:        ## create .env and generate secrets
	python3 scripts/init_env.py
up: setup     ## build & start everything with Docker (http://localhost:8080)
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f backend
test:         ## backend tests (no API key or network needed)
	cd backend && pip install -q -r requirements-dev.txt && python -m pytest -q
backend:
	cd backend && alembic upgrade head && uvicorn app.main:app --reload --port 8000
frontend:
	cd frontend && npm install && npm run dev
