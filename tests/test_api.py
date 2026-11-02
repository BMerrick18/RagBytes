from fastapi.testclient import TestClient

from shark_byte.main import app


def test_health_reports_version():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "dev"}


def test_methods_lists_chunkers_and_file_types():
    client = TestClient(app)
    body = client.get("/v1/methods").json()
    assert [(method["name"], method["path"]) for method in body["methods"]] == [
        ("basic", "/v1/chunk/basic"),
        ("structured", "/v1/chunk/structured"),
    ]
    assert all(method["description"] for method in body["methods"])
    assert ".pdf" in body["file_types"]


def test_openapi_documents_public_routes():
    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "RagBytes API"
    assert set(spec["paths"]) == {"/v1/chunk/basic", "/v1/chunk/structured", "/v1/methods", "/v1/stats", "/health"}
    structured = spec["paths"]["/v1/chunk/structured"]["post"]
    assert structured["tags"] == ["chunking"]
    assert list(structured["requestBody"]["content"]) == ["multipart/form-data"]


def test_each_listed_method_path_is_served():
    client = TestClient(app)
    for method in client.get("/v1/methods").json()["methods"]:
        response = client.post(method["path"], files={"file": ("notes.txt", b"Some text.", "text/plain")})
        assert response.status_code == 200, method["path"]


def test_cors_allows_any_origin():
    client = TestClient(app)
    response = client.options(
        "/v1/chunk/basic",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_invalid_pdf_returns_400():
    client = TestClient(app)
    response = client.post(
        "/v1/chunk/basic",
        files={"file": ("notes.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 400


def test_a_file_with_only_unreadable_regions_returns_400():
    client = TestClient(app)
    raw = b"| <table><tr><td>x</td></tr></table> |\n| --- |\n"
    for tier in ("basic", "structured"):
        response = client.post(f"/v1/chunk/{tier}", files={"file": ("layout.md", raw, "text/markdown")})

        assert response.status_code == 400, tier
        assert "scanned" in response.json()["detail"]


def test_unknown_tier_returns_404():
    client = TestClient(app)
    response = client.post(
        "/v1/chunk/telepathy",
        files={"file": ("notes.txt", b"Some text.", "text/plain")},
    )
    assert response.status_code == 404


def test_unsupported_file_type_returns_415():
    client = TestClient(app)
    response = client.post("/v1/chunk/basic", files={"file": ("notes.xlsx", b"x", "application/octet-stream")})
    assert response.status_code == 415
    assert response.json()["detail"] == "Unsupported file type: .xlsx"


def test_upload_returns_chunks_in_file_order():
    client = TestClient(app)
    raw = "\n".join(
        [
            "Guide",
            "=====",
            "",
            "Install the package.",
            "",
            "| Item | Picture |",
            "| --- | --- |",
            "| Plot | ![Plot](plot.png) |",
            "",
            "Then run it.",
            "",
        ]
    )
    response = client.post(
        "/v1/chunk/basic",
        files={"file": ("guide.md", raw.encode(), "text/markdown")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "guide.md"
    assert body["file_id"]
    assert "sections" not in body
    assert "all_sections" not in body
    assert "simple_sections" not in body
    assert "complex_sections" not in body
    chunks = body["chunks"]
    assert list(chunks[0]) == ["chunk_id", "metadata", "embed_text", "content"]
    assert chunks[0]["content"] == (
        "Guide\n\nInstall the package.\n\n| Item | Picture |\n| --- | --- |\n| Plot | [Image: Plot] |"
    )
    assert chunks[0]["embed_text"] == chunks[0]["content"]
    assert chunks[1]["embed_text"] == "Guide\n\n[Image: Plot]"
    assert chunks[1]["content"] == "[Image: Plot]"
    assert chunks[2]["content"] == "Then run it."
    assert chunks[0]["metadata"]["media_type"] is None
    assert chunks[1]["metadata"]["media_type"] is None
    assert [chunk["metadata"]["format"] for chunk in chunks] == ["text", "image", "text"]
    assert "complexity" not in chunks[0]["metadata"]
    assert [chunk["metadata"]["chunk_number"] for chunk in chunks] == [0, 1, 2]
    assert "index" not in chunks[0]["metadata"]
    assert "section_ids" not in chunks[0]["metadata"]
    assert "index" not in chunks[0]["metadata"]["details"]
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
    first = chunks[0]
    assert first["metadata"]["file_id"] == body["file_id"]
    assert first["metadata"]["filename"] == "guide.md"
    assert first["metadata"]["headings"] == ["Guide"]
    assert first["metadata"]["heading"] == "Guide"
    assert first["metadata"]["subheading"] is None
    assert first["metadata"]["page"] is None
    joined = "\n\n".join(chunk["content"] for chunk in chunks)
    for chunk in chunks:
        start = chunk["metadata"]["details"]["start"]
        end = chunk["metadata"]["details"]["end"]
        assert joined[start:end] == chunk["content"]
