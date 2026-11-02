from fastapi.testclient import TestClient

from ragbytes.config import settings
from ragbytes.main import app

NOTES = {"file": ("notes.txt", b"First paragraph.\n\nSecond paragraph.", "text/plain")}


def test_stats_start_at_zero():
    client = TestClient(app)
    assert client.get("/v1/stats").json() == {"documents": 0, "chunks": 0}


def test_each_chunked_document_is_counted():
    client = TestClient(app)
    first = client.post("/v1/chunk/basic", files=NOTES).json()
    second = client.post("/v1/chunk/structured", files=NOTES).json()
    assert client.get("/v1/stats").json() == {
        "documents": 2,
        "chunks": len(first["chunks"]) + len(second["chunks"]),
    }


def test_rejected_uploads_are_not_counted():
    client = TestClient(app)
    client.post("/v1/chunk/basic", files={"file": ("notes.xlsx", b"x", "application/octet-stream")})
    client.post("/v1/chunk/basic", files={"file": ("notes.pdf", b"not a pdf", "application/pdf")})
    assert client.get("/v1/stats").json() == {"documents": 0, "chunks": 0}


def test_chunking_still_works_when_the_count_cannot_be_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "stats_path", str(tmp_path))
    response = TestClient(app).post("/v1/chunk/basic", files=NOTES)
    assert response.status_code == 200
