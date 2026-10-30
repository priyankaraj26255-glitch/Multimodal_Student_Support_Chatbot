from .conftest import new_conv, parse_sse


def test_crud_and_search(client, auth, ai):
    cid = new_conv(client, auth)
    assert client.patch(f"/api/conversations/{cid}", json={"title": "Physics notes"}, headers=auth).json()["title"] == "Physics notes"
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "Explain quantum tunnelling"}, headers=auth)
    assert r.status_code == 200
    found = client.get("/api/conversations?q=tunnelling", headers=auth).json()
    assert [c["id"] for c in found] == [cid]
    assert client.get("/api/conversations?q=zzzz", headers=auth).json() == []
    detail = client.get(f"/api/conversations/{cid}", headers=auth).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert client.delete(f"/api/conversations/{cid}", headers=auth).status_code == 204
    assert client.get(f"/api/conversations/{cid}", headers=auth).status_code == 404


def test_ownership_isolation(client, auth, auth2):
    cid = new_conv(client, auth)
    for method, url in [("get", f"/api/conversations/{cid}"), ("delete", f"/api/conversations/{cid}")]:
        assert getattr(client, method)(url, headers=auth2).status_code == 404
    assert client.patch(f"/api/conversations/{cid}", json={"title": "x"}, headers=auth2).status_code == 404
    assert client.get("/api/conversations", headers=auth2).json() == []


def test_chat_stream_regenerate_and_title(client, auth, ai):
    cid = new_conv(client, auth)
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "Hello there"}, headers=auth)
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "meta" and "token" in names and names[-1] == "done"
    assert client.get(f"/api/conversations/{cid}", headers=auth).json()["title"] == "Hello there"
    first_id = events[-1][1]["message_id"]
    r2 = client.post(f"/api/conversations/{cid}/regenerate", headers=auth)
    assert parse_sse(r2.text)[-1][0] == "done"
    msgs = client.get(f"/api/conversations/{cid}", headers=auth).json()["messages"]
    assert len(msgs) == 2 and msgs[1]["id"] != first_id


def test_language_is_sent_to_model(client, auth, ai):
    cid = new_conv(client, auth)
    client.post(f"/api/conversations/{cid}/messages", json={"content": "hi", "language": "mr"}, headers=auth)
    assert "Marathi" in ai.calls[0][0]["content"]
    assert client.get(f"/api/conversations/{cid}", headers=auth).json()["language"] == "mr"


def test_ai_not_configured_returns_clear_error(client, auth, monkeypatch):
    from app.services import llm
    monkeypatch.setattr(llm.settings, "gemini_api_key", "")
    cid = new_conv(client, auth)
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "hi"}, headers=auth)
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
