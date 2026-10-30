"""Small in-memory sliding-window rate limiter (per process).
For multi-instance deployments swap for Redis (e.g. slowapi + redis)."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import get_settings

settings = get_settings()
_hits: dict[str, deque] = defaultdict(deque)
_calls = 0


def client_ip(request: Request) -> str:
    if settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check(key: str, limit: int, window: int = 60) -> None:
    global _calls
    if not settings.rate_limit_enabled:
        return
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        retry = max(1, int(window - (now - q[0])))
        raise HTTPException(429, "Too many requests. Please slow down and try again shortly.",
                            headers={"Retry-After": str(retry)})
    q.append(now)
    _calls += 1
    if _calls % 2000 == 0:  # prune idle keys
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > window]:
            _hits.pop(k, None)


def ip_limiter(scope: str, limit_attr: str):
    def dep(request: Request):
        _check(f"{scope}:{client_ip(request)}", getattr(settings, limit_attr))
    return dep


auth_limiter = ip_limiter("auth", "rate_limit_auth_per_minute")
default_limiter = ip_limiter("default", "rate_limit_default_per_minute")


def ai_limiter(request: Request):
    """Per-IP limit for expensive endpoints (LLM, OCR, uploads, audio)."""
    _check(f"ai:{client_ip(request)}", settings.rate_limit_ai_per_minute)
