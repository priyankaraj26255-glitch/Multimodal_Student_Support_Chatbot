# Multimodal AI Chatbot

Text, images, PDFs/documents, OCR and voice in one chat UI. **React + Tailwind** frontend, **FastAPI** backend, **PostgreSQL**, RAG with **FAISS**, **PyMuPDF**, **Tesseract OCR** (English/Hindi/Marathi). All AI features run through **Google Gemini**.

## Quick start (Docker – recommended)

```bash
python3 scripts/init_env.py      # creates .env, generates SECRET_KEY + DB password, asks for your Gemini key
docker compose up --build        # first build takes a few minutes
```
Open **http://localhost:8080**, register an account, chat. (Windows: use `python` instead of `python3`.)

## Run without Docker (SQLite, hot reload)

Requires Python 3.11+ and Node 18+. Optional: install Tesseract for local OCR. Without it, OCR automatically falls back to the Gemini vision model.

```bash
./scripts/run_local.sh           # Linux/macOS   |   .\scripts\run_local.ps1   (Windows PowerShell)
```
Or manually: `cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && alembic upgrade head && uvicorn app.main:app --reload`, then `cd frontend && npm install && npm run dev` → http://localhost:5173. API docs: http://localhost:8000/docs.

## Required API key

| Key | Where to get it | Used for |
|---|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey | chat + vision, embeddings (RAG), AI-vision OCR/handwriting |

**Without a key the app still starts**; AI features return a clear "not configured" message and the UI shows a banner. Model names are configurable via `GEMINI_CHAT_MODEL` and `GEMINI_EMBEDDING_MODEL` in `.env`.

> **Note:** Speech-to-text (Whisper) and text-to-speech are not available in Gemini mode, as Gemini has no native STT/TTS API. Audio UI features will show a clear "not available" message.

## Architecture

```
Browser (React) ──/api──► nginx ──► FastAPI ─┬─ routers: auth · conversations · chat(SSE) · files · documents · audio · users
                                             ├─ services: routing → chat_engine → llm (Gemini: chat/tools/embeddings)
                                             │            images · documents(PyMuPDF/DOCX) · ocr(Tesseract|Gemini vision) · retrieval(FAISS)
                                             └─ PostgreSQL (users, conversations, messages, files, chunks+embeddings, preferences)
                                                + upload volume (retention-limited)
```
**One chat turn:** `routing.plan_route` (deterministic intent router) → `chat_engine` builds context (RAG passages, whole-document map-reduce, images as vision input, OCR text, rolling summary) → streaming generation with **tool calling** (`search_documents`, `get_page`, `ocr_image`) → SSE events (`meta`, `token`, `tool`, `done`+sources, `error`) → saved.

```
backend/app/{main,config,database,models,schemas,security,ratelimit}.py
backend/app/routers/   auth conversations chat files documents audio users system
backend/app/services/  llm routing prompts chat_engine retrieval documents images ocr storage retention
backend/alembic/       migrations (0001 initial schema)        backend/tests/
frontend/src/          App.jsx · lib/api.js (SSE, upload progress) · hooks/ · components/
docker-compose.yml · .env.example · scripts/ · Makefile
```

## Configuration

Key `.env` variables:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** Your Gemini API key |
| `GEMINI_CHAT_MODEL` | `gemini-2.5-flash` | Chat + vision model |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Embeddings for RAG |
| `CHAT_FALLBACK_MODEL` | `gemini-1.5-flash` | Used if the primary model fails |
| `AI_PROVIDER` | `gemini` | AI backend (only `gemini` is supported) |

## Tests

`make test` (or `cd backend && pip install -r requirements-dev.txt && pytest`) – tests cover auth, ownership isolation, conversations/search, SSE chat + regenerate, image/PDF upload and validation, RAG citations, quiz routing, OCR review, audio endpoints, privacy deletion, rate limiting. They mock the Gemini provider, so no key or network is needed.

## Troubleshooting

| Problem | Fix |
|---|---|
| Banner "no AI API key" / 503 | Add `GEMINI_API_KEY` to `.env`, then restart: `docker compose up -d --force-recreate backend` |
| "Gemini rejected the key / model not found" | Check key validity at https://aistudio.google.com and verify `GEMINI_CHAT_MODEL` in `.env` |
| Backend exits: "Set SECRET_KEY…" | Run `python scripts/init_env.py` |
| Streaming appears all at once | A proxy is buffering – keep `proxy_buffering off` (already set in `nginx.conf`) |
| Scanned PDF has no text | Tesseract missing – install it, or upload clear images and use Gemini AI-vision OCR |
| Hindi/Marathi OCR poor | Ensure `tesseract-ocr-hin/mar` are installed; use the "AI vision" engine for handwriting |
| Port 8080/5432 busy | Change the port mapping in `docker-compose.yml` |
| 429 Too many requests | Raise `RATE_LIMIT_*` in `.env` |

## Security & privacy

- Secrets only in server env; none in frontend code.
- bcrypt passwords, JWT auth, per-user ownership checks on every resource.
- Uploads: magic-byte/Pillow content sniffing, size limits, per-user storage quota, images fully decoded and re-encoded (strips EXIF/GPS), DOCX zip-bomb guard, PDF page limit, random server-side file names.
- Rate limiting (per IP), request-size guard, security headers + CSP (nginx), CORS allow-list.
- Logs contain paths/status/ids only (no message text, emails, or query strings); files auto-delete after `FILE_RETENTION_DAYS`; one-click deletion of chats/files/account.
