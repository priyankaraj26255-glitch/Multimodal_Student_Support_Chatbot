import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders

from .config import get_settings
from .logging_config import setup_logging
from .ratelimit import default_limiter
from .routers import audio, auth, chat, conversations, documents, files, system, users
from .services import llm
from .services.retention import cleanup_expired_files

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("app")


async def _retention_loop():
    while True:
        try:
            await run_in_threadpool(cleanup_expired_files)
        except Exception:
            log.warning("retention cleanup failed", exc_info=False)
        await asyncio.sleep(6 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment == "production" and (settings.secret_key == "change-me-in-production" or len(settings.secret_key) < 32):
        raise RuntimeError("Set SECRET_KEY (32+ random characters) before running in production. "
                           "Run `python scripts/init_env.py` to generate one.")
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    if not llm.is_configured():
        log.warning("GEMINI_API_KEY is not set – AI features will return a clear 'not configured' error.")
    task = asyncio.create_task(_retention_loop())
    yield
    task.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


class MetaMiddleware:
    """Pure-ASGI middleware (safe for streaming): request id, body-size guard,
    security headers and privacy-conscious access logging (no query strings/bodies)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        start, rid, status = time.perf_counter(), uuid.uuid4().hex[:12], {"code": 0}
        cl = dict(scope["headers"]).get(b"content-length")
        if cl and cl.isdigit() and int(cl) > (settings.max_doc_mb + 1) * 1024 * 1024:
            return await JSONResponse({"detail": "Request body too large."}, status_code=413)(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                h = MutableHeaders(scope=message)
                h["X-Request-ID"] = rid
                h["X-Content-Type-Options"] = "nosniff"
                h["X-Frame-Options"] = "DENY"
                h["Referrer-Policy"] = "no-referrer"
                h["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info("%s %s -> %s %.0fms rid=%s", scope["method"], scope["path"], status["code"],
                     (time.perf_counter() - start) * 1000, rid)


app.add_middleware(MetaMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"])


@app.exception_handler(llm.AIUnavailable)
async def ai_unavailable_handler(request: Request, exc: llm.AIUnavailable):
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Internal server error."}, status_code=500)


for r in (auth.router, conversations.router, chat.router, files.router, documents.router,
          audio.router, users.router, system.router):
    app.include_router(r, prefix="/api", dependencies=[Depends(default_limiter)])
