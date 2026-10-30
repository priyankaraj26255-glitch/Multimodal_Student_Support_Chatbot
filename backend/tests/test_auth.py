from .conftest import register


def test_register_login_me(client):
    h = register(client)
    assert client.get("/api/auth/me", headers=h).json()["email"] == "alice@mailtest.dev"
    r = client.post("/api/auth/login", json={"email": "ALICE@mailtest.dev", "password": "correct-horse-1"})
    assert r.status_code == 200 and r.json()["access_token"]


def test_duplicate_and_bad_credentials(client):
    register(client)
    assert client.post("/api/auth/register", json={"email": "alice@mailtest.dev", "password": "another-pass-1"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "alice@mailtest.dev", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@mailtest.dev", "password": "x"}).status_code == 401


def test_validation_and_unauthenticated(client):
    assert client.post("/api/auth/register", json={"email": "bad", "password": "short"}).status_code == 422
    assert client.get("/api/conversations").status_code == 401
    assert client.get("/api/conversations", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_health_and_capabilities(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert "ai_configured" in client.get("/api/capabilities").json()
