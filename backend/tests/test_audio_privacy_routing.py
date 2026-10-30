from app.services.routing import plan_route
from .conftest import new_conv, make_png
from .test_files import upload


def test_transcribe_and_speech(client, auth, ai):
    r = client.post("/api/audio/transcribe", files={"audio": ("a.webm", b"fakeaudio", "audio/webm;codecs=opus")},
                    data={"language": "hi"}, headers=auth)
    assert r.json() == {"text": "hello from voice"}
    assert client.post("/api/audio/transcribe", files={"audio": ("a.exe", b"x", "application/x-msdownload")}, headers=auth).status_code == 415
    s = client.post("/api/audio/speech", json={"text": "# Title\n**bold** `code`"}, headers=auth)
    assert s.status_code == 200 and s.headers["content-type"] == "audio/mpeg" and s.content.startswith(b"ID3")


def test_preferences_and_personalization_optout(client, auth):
    p = client.put("/api/preferences", json={"language": "hi", "personalization_enabled": True,
                                              "about_me": "I study CS"}, headers=auth).json()
    assert p["about_me"] == "I study CS" and p["language"] == "hi"
    p = client.put("/api/preferences", json={"language": "hi", "personalization_enabled": False,
                                              "about_me": "I study CS"}, headers=auth).json()
    assert p["about_me"] == ""


def test_delete_history_and_account(client, auth, ai):
    f = upload(client, auth, "n.txt", b"some text content").json()
    cid = new_conv(client, auth)
    client.post(f"/api/conversations/{cid}/messages", json={"content": "hi", "attachment_ids": [f["id"]]}, headers=auth)
    assert client.delete("/api/me/history", headers=auth).status_code == 204
    assert client.get("/api/conversations", headers=auth).json() == []
    assert client.get(f"/api/files/{f['id']}/content", headers=auth).status_code == 404
    assert client.delete("/api/me", headers=auth).status_code == 204
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_routing():
    assert plan_route("hi").intents == ["text"]
    r = plan_route("Extract the text from this", images=1)
    assert r.needs_vision and r.needs_ocr
    assert plan_route("Make flashcards", docs=1).mode == "flashcards"
    assert plan_route("Give me a summary", docs=1).mode == "summary"
    assert plan_route("Compare these two", docs=2).mode == "compare"
    assert plan_route("Compare these two", docs=1).mode is None
    assert plan_route("What does chapter 2 say?", docs=1).needs_retrieval
    assert "speech" in plan_route("hello", input_mode="voice").intents
    assert plan_route("मुझे क्विज़ बनाओ", docs=1).mode == "quiz"


def test_rate_limit(client, monkeypatch):
    from app import ratelimit
    monkeypatch.setattr(ratelimit.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(ratelimit.settings, "rate_limit_auth_per_minute", 3)
    ratelimit._hits.clear()
    codes = [client.post("/api/auth/login", json={"email": "a@mailtest.dev", "password": "x"}).status_code for _ in range(5)]
    assert codes[-1] == 429 and codes[0] == 401
    ratelimit._hits.clear()
