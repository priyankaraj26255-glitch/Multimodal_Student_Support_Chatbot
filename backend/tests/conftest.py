import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="mmchat-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "UPLOAD_DIR": f"{_tmp}/uploads",
    "SECRET_KEY": "test-secret-key-for-tests-only-0123456789",
    "GEMINI_API_KEY": "sk-test-gemini",
    "RATE_LIMIT_ENABLED": "false",
    "ENVIRONMENT": "test",
})

import io  # noqa: E402
import json  # noqa: E402

import pymupdf as fitz  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import llm  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


class FakeAI:
    def __init__(self):
        self.calls: list[list[dict]] = []

    async def stream_chat(self, messages, tools=None, tool_runner=None, max_rounds=3):
        self.calls.append(messages)
        last = messages[-1]["content"]
        text = last if isinstance(last, str) else last[0]["text"]
        for tok in ("Echo: ", text[:40]):
            yield {"type": "token", "text": tok}

    async def complete(self, messages, model=None):
        return "COMPLETED"

    async def embed(self, texts):
        out = np.zeros((len(texts), 64), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in t.lower().split():
                out[i, hash(w.strip(".,?!")) % 64] += 1
        return out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)

    async def transcribe(self, data, filename, ctype, language):
        return "hello from voice"

    async def synthesize(self, text, voice):
        return b"ID3fake-mp3"


@pytest.fixture
def ai(monkeypatch):
    fake = FakeAI()
    for name in ("stream_chat", "complete", "embed", "transcribe", "synthesize"):
        monkeypatch.setattr(llm, name, getattr(fake, name))
    return fake


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client, email="alice@mailtest.dev", password="correct-horse-1"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


@pytest.fixture
def auth2(client):
    return register(client, "bob@mailtest.dev")


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        ev = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((ev, data))
    return events


def make_png(w=120, h=90, color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def make_pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for t in pages:
        doc.new_page().insert_text((72, 100), t)
    return doc.tobytes()


def new_conv(client, auth) -> str:
    return client.post("/api/conversations", json={}, headers=auth).json()["id"]
