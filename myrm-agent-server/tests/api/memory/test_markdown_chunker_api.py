"""Integration tests for incremental sliding window Markdown chunker API.

[POS]
Integration test verifying sliding window slicing, incremental diff indexing,
token savings telemetry, and context hydration endpoints.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.markdown_chunker (router, get_markdown_chunker_service)
- app.services.memory.markdown_chunker (MarkdownChunkerService)
- app.schemas.markdown_chunker (
    ChunkSliceRequest,
    HydrateRequest,
    IncrementalIndexRequest,
  )

[OUTPUT]
- Test functions covering markdown chunker API.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.markdown_chunker import (
    get_markdown_chunker_service,
)
from app.api.memory.markdown_chunker import (
    router as markdown_chunker_router,
)
from app.services.memory.markdown_chunker.provider import (
    MarkdownChunkerService,
)


@pytest.fixture
def isolated_service() -> MarkdownChunkerService:
    """Create isolated markdown chunker service instance."""
    return MarkdownChunkerService()


@pytest.fixture
def test_app(isolated_service: MarkdownChunkerService) -> FastAPI:
    """Create FastAPI test application with injected isolated service."""
    api_app = FastAPI()
    api_app.include_router(markdown_chunker_router, prefix="/api/memory")
    api_app.dependency_overrides[get_markdown_chunker_service] = lambda: isolated_service
    return api_app


@pytest.mark.asyncio
async def test_slice_markdown_endpoint(test_app: FastAPI) -> None:
    """Verify /slice endpoint breaks content into structured chunks with line pointers."""
    content = (
        "# Engineering Handbook\n\n"
        "Chapter 1: Code Reliability\n"
        "Ensure all functions have explicit types.\n\n"
        "Chapter 2: Performance Bounds\n"
        "Always evaluate computational complexity.\n"
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/chunker/slice",
            json={
                "content": content,
                "source_path": "docs/handbook.md",
                "config": {
                    "target_tokens": 15,
                    "overlap_tokens": 5,
                    "chars_per_token": 3.0,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_path"] == "docs/handbook.md"
        assert data["total_chunks"] >= 1
        chunks = data["chunks"]
        first = chunks[0]
        assert first["start_line"] == 1
        assert first["end_line"] >= 1
        assert len(first["chunk_hash"]) == 16
        assert first["token_estimate"] > 0


@pytest.mark.asyncio
async def test_incremental_index_endpoint_and_savings(test_app: FastAPI) -> None:
    """Verify /incremental-index caches chunks and calculates token savings on minor updates."""
    content_v1 = (
        "## Section Alpha\n\n"
        "Core rule: Zero Any types across whole system.\n\n"
        "## Section Beta\n\n"
        "Performance rule: Benchmark latency under 10ms.\n"
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. First indexing run (fresh)
        resp1 = await client.post(
            "/api/memory/chunker/incremental-index",
            json={
                "source_path": "MEMORY.md",
                "new_content": content_v1,
                "config": {"target_tokens": 20, "overlap_tokens": 5, "chars_per_token": 3.0},
            },
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        report1 = data1["report"]
        assert report1["status"] == "fully_reindexed"
        assert report1["reused_chunks"] == 0
        assert report1["changed_chunks"] > 0

        # 2. Second indexing run with minor append
        content_v2 = content_v1 + "\n\n## Section Gamma\n\nNew appended note here.\n"
        resp2 = await client.post(
            "/api/memory/chunker/incremental-index",
            json={
                "source_path": "MEMORY.md",
                "new_content": content_v2,
                "config": {"target_tokens": 20, "overlap_tokens": 5, "chars_per_token": 3.0},
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        report2 = data2["report"]
        assert report2["status"] == "partially_updated"
        assert report2["reused_chunks"] > 0
        assert report2["token_savings_pct"] > 40.0


@pytest.mark.asyncio
async def test_hydrate_endpoint(test_app: FastAPI) -> None:
    """Verify /hydrate expands document lines around target chunk."""
    doc = (
        "Line 1: Header title\n"
        "Line 2: Important background\n"
        "Line 3: Core theorem statement\n"
        "Line 4: Crucial proof step\n"
        "Line 5: Summary conclusion\n"
    )

    target_chunk = {
        "chunk_id": "test_chk_1",
        "source_path": "math.md",
        "start_line": 3,
        "end_line": 4,
        "char_start": 44,
        "char_end": 96,
        "text": "Line 3: Core theorem statement\nLine 4: Crucial proof step\n",
        "chunk_hash": "hash123",
        "token_estimate": 15,
        "is_truncated": False,
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/chunker/hydrate",
            json={
                "chunk": target_chunk,
                "full_document": doc,
                "window_lines": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        hydrated = data["hydrated_text"]
        # Must include line 2 (window line before line 3)
        assert "Line 2" in hydrated
        assert "Core theorem statement" in hydrated
        assert "Line 5" in hydrated
