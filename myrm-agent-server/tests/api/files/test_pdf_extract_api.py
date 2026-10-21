"""Integration tests for PDF extraction API endpoint /files/extract-pdf.

Covers:
- Successful extraction with default max_pages=500
- parsed_pages field in response
- filePath mode for local files
- Validation errors (max_pages bounds, missing params)
- Edge cases: non-PDF, maxPages=1, response schema completeness
"""

from unittest.mock import AsyncMock, patch

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
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("latin-1") + stream_bytes + b"\nendstream\nendobj\n",
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


def _build_pdf_with_figure_bytes(text: str) -> bytes:
    """Build a PDF whose page carries one embedded figure.

    The extractor only reports ``images``/``imageTrace`` when a figure survives the ablation
    filter, so the camelCase wire-contract guard needs a document that actually carries one.
    """
    stream_content = f"BT /F1 12 Tf 72 740 Td ({text}) Tj ET\n" + "q 120 0 0 120 72 480 cm /Im0 Do Q"
    stream_bytes = stream_content.encode("latin-1")
    # Deterministic, non-uniform pixels: the filter drops flat or tiny crops.
    figure = bytes((index * 37 + 11) % 256 for index in range(80 * 60 * 3))

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> /XObject << /Im0 6 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1") + stream_bytes + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"6 0 obj\n<< /Type /XObject /Subtype /Image /Width 80 /Height 60 /ColorSpace /DeviceRGB "
        f"/BitsPerComponent 8 /Length {len(figure)} >>\nstream\n".encode("latin-1")
        + figure
        + b"\nendstream\nendobj\n",
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
def pdf_with_figure(tmp_path) -> str:
    path = str(tmp_path / "figure.pdf")
    with open(path, "wb") as f:
        f.write(_build_pdf_with_figure_bytes("Section One " * 40))
    return path


def _build_mixed_scan_pdf_bytes() -> bytes:
    """Two-page PDF: page 1 has a text layer, page 2 is a graphic-only scan page.

    Reproduces the silent-loss shape: the document clears the whole-text threshold, yet
    page 2 carries no text at all, so ``pagesWithoutText`` must name it.
    """
    text_stream = ("BT /F1 12 Tf 72 740 Td (" + "Body text that clears the sparse threshold " * 8 + ") Tj ET").encode("latin-1")
    # A scanned page is an embedded bitmap, not a flat rectangle: the ablation filter drops
    # flat fills, so a solid rect would never reach the client as an image.
    scan_stream = b"q 480 0 0 640 60 60 cm /Im0 Do Q"
    scan_pixels = bytes((index * 37 + 11) % 256 for index in range(80 * 60 * 3))

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 7 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(text_stream)} >>\nstream\n".encode("latin-1") + text_stream + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 6 0 R /Resources << /XObject << /Im0 8 0 R >> >> >>\nendobj\n",
        f"6 0 obj\n<< /Length {len(scan_stream)} >>\nstream\n".encode("latin-1") + scan_stream + b"\nendstream\nendobj\n",
        b"7 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"8 0 obj\n<< /Type /XObject /Subtype /Image /Width 80 /Height 60 /ColorSpace /DeviceRGB "
        f"/BitsPerComponent 8 /Length {len(scan_pixels)} >>\nstream\n".encode("latin-1")
        + scan_pixels
        + b"\nendstream\nendobj\n",
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
def pdf_with_scan_page(tmp_path) -> str:
    path = str(tmp_path / "mixed.pdf")
    with open(path, "wb") as f:
        f.write(_build_mixed_scan_pdf_bytes())
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
    async def test_extract_pdf_parsed_pages_equals_page_count(self, client: AsyncClient, pdf_file: str):
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
        required_keys = {"text", "images", "pageCount", "parsedPages", "pagesWithoutText", "strategy", "tables", "imageTrace"}
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
    async def test_nested_response_fields_are_camel_case(self, client: AsyncClient, pdf_with_figure: str):
        """Nested payloads must reach the client in the casing the frontend reads.

        Declared fields camelize through ``alias_generator``, but plain dicts and models
        without that config do not: the frontend reads ``mimeType``/``fileUrl`` off images
        and ``droppedCount``/``keptCount`` off the trace, so a snake_case payload disables
        the image URL and the toast without raising anywhere.
        """
        resp = await client.post(
            "/api/v1/files/extract-pdf",
            json={"filePath": pdf_with_figure},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["images"], "the fixture page carries one figure that survives the filter"
        trace = data["imageTrace"]
        assert trace, "the trace is populated whenever the document carried images"
        assert "totalProcessed" in trace
        assert "droppedCount" in trace
        assert not [key for key in trace if "_" in key], f"snake_case trace keys: {sorted(trace)}"

        for image in data["images"]:
            assert "mimeType" in image
            assert "fileUrl" in image
            assert not [key for key in image if "_" in key], f"snake_case image keys: {sorted(image)}"

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

    @pytest.mark.anyio
    async def test_trace_truncated_flag_reaches_the_client(self, client: AsyncClient, pdf_file: str):
        """The trace's ``truncated`` flag must survive serialization, not just exist in the model.

        A capped figure scan is the only case that sets it, and the frontend gates its
        ``chat.pdfFiguresTruncated`` toast on reading that key. The endpoint takes no OCR
        window and the default ceiling (30 figures) is far above any cheap fixture, so the
        extractor is stubbed at its boundary rather than generating a 30-figure document.
        """
        from myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor import PDFExtractResult

        capped = PDFExtractResult(
            text="body",
            page_count=40,
            parsed_pages=40,
            strategy="text",
            image_trace={
                "total_processed": 30,
                "kept_count": 30,
                "dropped_count": 0,
                "drop_reasons": {},
                "truncated": True,
            },
        )

        with patch(
            "app.services.files.content_extraction.extract_pdf_from_path",
            new=AsyncMock(return_value=capped),
        ):
            resp = await client.post("/api/v1/files/extract-pdf", json={"filePath": pdf_file})

        assert resp.status_code == 200
        trace = resp.json()["data"]["imageTrace"]
        # A single-word key such as ``truncated`` survives even a broken serializer, so the
        # snake_case key guards the serializer itself and the boolean guards the flag.
        assert trace["truncated"] is True, "the frontend gates its figure toast on this flag"
        assert "dropReasons" in trace, "a raw dict reaches the client verbatim without the serializer"

    @pytest.mark.anyio
    async def test_pages_without_text_reaches_the_client(self, client: AsyncClient, pdf_with_scan_page: str):
        """A partly scanned PDF must name its unreadable pages on the wire.

        ``parsedPages`` counts the delivery window and stays equal to ``pageCount`` here,
        so without this field the scan page is invisible to both the user and the model.
        """
        resp = await client.post("/api/v1/files/extract-pdf", json={"filePath": pdf_with_scan_page})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pageCount"] == 2
        assert data["pagesWithoutText"] == [2], "the graphic-only page is the one with no text layer"
        assert data["parsedPages"] == data["pageCount"], "the delivery window covered both pages"

    @pytest.mark.anyio
    async def test_image_items_carry_their_source_page_number(self, client: AsyncClient, pdf_with_scan_page: str):
        """Each delivered image must name its source page on the wire.

        The frontend splits "sent as images" from "withheld by the delivery ceiling" by
        matching ``pagesWithoutText`` against the image page numbers; without this field
        every scanned page would look delivered.
        """
        resp = await client.post("/api/v1/files/extract-pdf", json={"filePath": pdf_with_scan_page})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["images"], "the scanned page is delivered as an image"
        page_numbers = [image["pageNumber"] for image in data["images"]]
        assert page_numbers == data["pagesWithoutText"]
