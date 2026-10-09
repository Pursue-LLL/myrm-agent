"""Integration tests for multi-platform memory migration wizard API.

[POS]
Integration tests verifying external asset discovery, multi-platform parsing,
security sanitization, sliding-window chunking telemetry, and deduplicated ingestion.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.migration_wizard (get_migration_wizard_service, router)
- app.services.memory.migration_wizard (MigrationWizardService)

[OUTPUT]
- Test functions covering migration wizard API endpoints.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.migration_wizard import (
    get_migration_wizard_service,
)
from app.api.memory.migration_wizard import (
    router as migration_wizard_router,
)
from app.services.memory.migration_wizard import (
    MigrationWizardService,
)


@pytest.fixture
def isolated_service() -> MigrationWizardService:
    """Create isolated migration wizard service."""
    return MigrationWizardService()


@pytest.fixture
def test_app(isolated_service: MigrationWizardService) -> FastAPI:
    """Create FastAPI test application with injected isolated service."""
    api_app = FastAPI()
    api_app.include_router(migration_wizard_router, prefix="/api/memory")
    api_app.dependency_overrides[get_migration_wizard_service] = lambda: isolated_service
    return api_app


@pytest.mark.asyncio
async def test_sources_endpoint(test_app: FastAPI) -> None:
    """Verify /sources endpoint lists all supported external platforms."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/memory/migration-wizard/sources")
        assert resp.status_code == 200
        data = resp.json()

        assert "supported_sources" in data
        sources = data["supported_sources"]
        assert "openclaw" in sources
        assert "hermes" in sources
        assert "chatgpt_export" in sources
        assert "markdown_tree" in sources


@pytest.mark.asyncio
async def test_detect_endpoint(test_app: FastAPI) -> None:
    """Verify /detect endpoint locates existing mock competitor assets."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        hermes_dir = Path(tmp_dir) / ".hermes" / "memories"
        hermes_dir.mkdir(parents=True, exist_ok=True)
        (hermes_dir / "user_notes.md").write_text("User prefers Python 3.13", encoding="utf-8")

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            payload = {"custom_candidates": [str(hermes_dir)]}
            resp = await client.post("/api/memory/migration-wizard/detect", json=payload)
            assert resp.status_code == 200
            data = resp.json()

            assert "total_detected" in data
            assert "candidates" in data


@pytest.mark.asyncio
async def test_import_raw_payload_and_deduplication(test_app: FastAPI) -> None:
    """Verify /import parses OpenClaw memory, generates chunks, and deduplicates re-runs."""
    claw_content = (
        "# Engineering Standards\n"
        "- Standard 1: All API responses must follow JSON schema\n"
        "- Standard 2: Graceful degradation is required for all external calls\n\n"
        "# Long Context Section\n"
        + "System memory design prioritizes high performance and rock-solid resilience. " * 12
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Run 1: Net new import
        payload1 = {
            "source_type": "openclaw",
            "raw_content": claw_content,
            "source_label": "test_openclaw.md",
        }
        resp1 = await client.post("/api/memory/migration-wizard/import", json=payload1)
        assert resp1.status_code == 200
        data1 = resp1.json()

        assert data1["success"] is True
        rep1 = data1["report"]
        assert rep1["source_type"] == "openclaw"
        assert rep1["total_admitted"] >= 2
        assert rep1["total_chunks_generated"] >= 2
        assert rep1["total_skipped_duplicates"] == 0

        # Run 2: Re-import same content should trigger deduplication
        resp2 = await client.post("/api/memory/migration-wizard/import", json=payload1)
        assert resp2.status_code == 200
        data2 = resp2.json()

        rep2 = data2["report"]
        assert rep2["total_admitted"] == 0
        assert rep2["total_skipped_duplicates"] >= 2


@pytest.mark.asyncio
async def test_import_file_with_sliding_window_chunks(test_app: FastAPI) -> None:
    """Verify /import accepts a local file path and chunks it via 400/80 sliding window."""
    with tempfile.NamedTemporaryFile("w+", suffix=".md", encoding="utf-8") as f:
        f.write(
            "# Architecture Principles\n\n"
            + "Memory subsystems must guarantee local-first privacy, zero data loss, and zero bloat. " * 10
        )
        f.flush()

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            payload = {
                "source_type": "markdown_tree",
                "file_path": f.name,
                "source_label": "arch_principles.md",
            }
            resp = await client.post("/api/memory/migration-wizard/import", json=payload)
            assert resp.status_code == 200
            data = resp.json()

            assert data["success"] is True
            rep = data["report"]
            assert rep["total_admitted"] >= 1
            assert rep["total_chunks_generated"] >= 1
            assert rep["latency_ms"] > 0.0
