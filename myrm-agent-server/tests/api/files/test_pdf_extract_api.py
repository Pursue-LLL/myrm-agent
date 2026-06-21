"""Integration tests for PDF extraction API endpoint /files/extract-pdf.

Covers:
- Successful extraction with default max_pages=500
- parsed_pages field in response
- filePath mode for local files
- Validation errors (max_pages bounds, missing params)
- Edge cases: non-PDF, maxPages=1, response schema completeness
"""

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="files")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _build_minimal_pdf_bytes(text: str) -> bytes:
    """Build a minimal valid PDF 1.4 with a single text page."""
    stream_content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    stream_bytes = stream_content.encode("latin-1")
    stream_len = len(stream_bytes)

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("latin-1")
        + stream_bytes
        + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    body = b""
    offsets: list[int] = []
    header = b"%PDF-1.4\n"
    pos = len(header)

    for obj in objects:
        offsets.append(pos)
        body += obj
        pos += len(obj)

    xref_pos = pos
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets:
        xref += f"{offset:010d} 00000 n \n"

    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    return header + body + xref.encode("latin-1") + trailer.encode("latin-1")


@pytest.fixture
def pdf_file(tmp_path) -> str:
    path = str(tmp_path / "test.pdf")
    with open(path, "wb") as f:
        f.write(_build_minimal_pdf_bytes("Hello World " * 20))
    return path


class TestPDFExtractAPI:
    """Integration tests for /files/extract-pdf endpoint."""

    @pytest.mark.anyio
    async def test_extract_pdf_local_mode(self, client: AsyncClient, pdf_file: str):
        """POST with filePath should extract text and return parsed_pages."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "parsedPages" in data
        assert data["parsedPages"] >= 1
        assert data["pageCount"] >= 1
        assert data["parsedPages"] <= data["pageCount"]
        assert data["strategy"] in ("text", "hybrid")

    @pytest.mark.anyio
    async def test_extract_pdf_parsed_pages_equals_page_count(
        self, client: AsyncClient, pdf_file: str
    ):
        """For a small PDF, parsedPages should equal pageCount."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["parsedPages"] == data["pageCount"]

    @pytest.mark.anyio
    async def test_max_pages_accepts_large_value(self, client: AsyncClient, pdf_file: str):
        """maxPages up to 2000 should be accepted."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file, "maxPages": 2000},
        )
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_max_pages_rejects_over_limit(self, client: AsyncClient, pdf_file: str):
        """maxPages > 2000 should be rejected by validation."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file, "maxPages": 2001},
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.anyio
    async def test_max_pages_rejects_zero(self, client: AsyncClient, pdf_file: str):
        """maxPages < 1 should be rejected."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file, "maxPages": 0},
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.anyio
    async def test_missing_params_returns_error(self, client: AsyncClient):
        """Neither filePath nor fileId should return validation error."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={},
        )
        assert resp.status_code in (400, 422, 500)

    @pytest.mark.anyio
    async def test_nonexistent_file_returns_404(self, client: AsyncClient):
        """Non-existent filePath should return 404."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": "/nonexistent/fake.pdf"},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_non_pdf_file_returns_error(self, client: AsyncClient, tmp_path):
        """A .txt file should be rejected as unsupported."""
        txt_file = str(tmp_path / "test.txt")
        with open(txt_file, "w") as f:
            f.write("not a pdf")
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": txt_file},
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.anyio
    async def test_max_pages_boundary_one(self, client: AsyncClient, pdf_file: str):
        """maxPages=1 is the minimum valid value."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file, "maxPages": 1},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["parsedPages"] >= 1

    @pytest.mark.anyio
    async def test_max_pages_negative_rejected(self, client: AsyncClient, pdf_file: str):
        """Negative maxPages should be rejected."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file, "maxPages": -1},
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.anyio
    async def test_response_schema_completeness(self, client: AsyncClient, pdf_file: str):
        """Response must contain all expected camelCase fields."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        required_keys = {"text", "images", "pageCount", "parsedPages", "strategy", "tables", "imageTrace"}
        assert required_keys.issubset(set(data.keys()))

    @pytest.mark.anyio
    async def test_tables_field_is_list(self, client: AsyncClient, pdf_file: str):
        """tables field should always be a list."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["tables"], list)

    @pytest.mark.anyio
    async def test_custom_max_pages_500(self, client: AsyncClient, pdf_file: str):
        """Default maxPages=500 should work."""
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_file, "maxPages": 500},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["parsedPages"] == data["pageCount"]
