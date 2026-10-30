from .conftest import make_pdf, make_png, new_conv, parse_sse


def upload(client, auth, name, data, ctype="application/octet-stream"):
    return client.post("/api/files/upload", files={"file": (name, data, ctype)}, headers=auth)


def test_rejects_unsupported_empty_and_corrupt(client, auth):
    assert upload(client, auth, "virus.exe", b"MZ\x90\x00binary").status_code == 415
    assert upload(client, auth, "empty.txt", b"").status_code == 400
    assert upload(client, auth, "fake.png", b"not really a png").status_code == 415
    assert upload(client, auth, "bad.pdf", b"%PDF-1.4 garbage").status_code == 422


def test_size_limits(client, auth, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "max_doc_mb", 1)
    monkeypatch.setattr(s, "max_image_mb", 1)
    r = upload(client, auth, "big.txt", b"a" * (2 * 1024 * 1024))
    assert r.status_code == 413


def test_image_upload_and_vision_chat(client, auth, ai):
    r = upload(client, auth, "red.png", make_png())
    assert r.status_code == 201 and r.json()["kind"] == "image"
    fid = r.json()["id"]
    assert client.get(f"/api/files/{fid}/content", headers=auth).headers["content-type"].startswith("image/")
    cid = new_conv(client, auth)
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "What colour is this?", "attachment_ids": [fid]}, headers=auth)
    last = ai.calls[0][-1]["content"]
    assert any(p.get("type") == "image_url" for p in last)
    # follow-up without re-attaching still sees the image
    client.post(f"/api/conversations/{cid}/messages", json={"content": "And its size?"}, headers=auth)
    assert any(p.get("type") == "image_url" for p in ai.calls[1][-1]["content"])


def test_pdf_rag_with_citations(client, auth, ai):
    pdf = make_pdf(["Introduction to cooking pasta and sauces.", "The capital of France is Paris, a large city."])
    r = upload(client, auth, "notes.pdf", pdf)
    assert r.status_code == 201, r.text
    assert r.json()["page_count"] == 2
    cid = new_conv(client, auth)
    resp = client.post(f"/api/conversations/{cid}/messages",
                       json={"content": "What is the capital of France?", "attachment_ids": [r.json()["id"]]}, headers=auth)
    done = parse_sse(resp.text)[-1][1]
    assert done["sources"] and done["sources"][0]["page"] == 2
    ctx = [m["content"] for m in ai.calls[0] if m["role"] == "system"][-1]
    assert "notes.pdf, p. 2" in ctx
    saved = client.get(f"/api/conversations/{cid}", headers=auth).json()["messages"][-1]
    assert saved["sources"][0]["filename"] == "notes.pdf"


def test_quiz_mode_uses_whole_document(client, auth, ai):
    f = upload(client, auth, "bio.txt", b"Mitochondria are the powerhouse of the cell.\n\nRibosomes make proteins.").json()
    cid = new_conv(client, auth)
    resp = client.post(f"/api/conversations/{cid}/messages",
                       json={"content": "Make a quiz from this", "attachment_ids": [f["id"]]}, headers=auth)
    meta = parse_sse(resp.text)[0][1]
    assert meta["route"]["mode"] == "quiz"
    assert "Mitochondria" in [m["content"] for m in ai.calls[0] if m["role"] == "system"][-1]


def test_documents_query_and_generate(client, auth, ai):
    a = upload(client, auth, "a.txt", b"Alpha document about solar panels and energy.").json()
    b = upload(client, auth, "b.txt", b"Beta document about wind turbines and power.").json()
    q = client.post("/api/documents/query", json={"question": "solar panels", "file_ids": [a["id"]]}, headers=auth).json()
    assert q["found"] and q["answer"] == "COMPLETED"
    g = client.post("/api/documents/generate", json={"mode": "compare", "file_ids": [a["id"], b["id"]]}, headers=auth)
    assert g.status_code == 200 and g.json()["content"] == "COMPLETED"
    assert client.post("/api/documents/generate", json={"mode": "compare", "file_ids": [a["id"]]}, headers=auth).status_code == 400


def test_file_ownership_and_delete(client, auth, auth2):
    f = upload(client, auth, "x.txt", b"private notes here").json()
    assert client.get(f"/api/files/{f['id']}/content", headers=auth2).status_code == 404
    assert client.delete(f"/api/files/{f['id']}", headers=auth2).status_code == 404
    assert client.post("/api/documents/query", json={"question": "notes", "file_ids": [f["id"]]}, headers=auth2).status_code == 404
    assert client.delete(f"/api/files/{f['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/files/{f['id']}/content", headers=auth).status_code == 404


def test_ocr_review_flow(client, auth, ai, monkeypatch):
    from app.services import ocr
    async def fake_ocr(data, mime, engine="auto"):
        return ocr.OCRResult(text="Hello OCR", engine="tesseract", confidence=88.0)
    monkeypatch.setattr(ocr, "run_ocr", fake_ocr)
    f = upload(client, auth, "scan.png", make_png()).json()
    r = client.post(f"/api/files/{f['id']}/ocr", json={"engine": "auto"}, headers=auth)
    assert r.json()["text"] == "Hello OCR"
    client.put(f"/api/files/{f['id']}/text", json={"text": "Hello corrected OCR"}, headers=auth)
    assert client.get(f"/api/files/{f['id']}/text", headers=auth).json()["text"] == "Hello corrected OCR"
    cid = new_conv(client, auth)
    client.post(f"/api/conversations/{cid}/messages", json={"content": "explain", "attachment_ids": [f["id"]]}, headers=auth)
    assert any("Hello corrected OCR" in str(m["content"]) for m in ai.calls[0])
