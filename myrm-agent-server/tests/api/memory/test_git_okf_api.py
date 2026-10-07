# [POS]: tests/api/memory/test_git_okf_api.py
# [INPUT]: Isolated FastAPI test application, AsyncClient, and temporary OKF knowledge bundle files.
# [OUTPUT]: Integration tests verifying bundle loading, BM25 search, rot validation, and progressive disclosure APIs.

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.git_okf_router import router as git_okf_router
from app.services.memory.git_okf_service import GitOKFService, get_git_okf_service


@pytest.fixture
def sample_bundle_dir(tmp_path: Path) -> Path:
    """Prepares a temporary directory structured as a Google OKF v0.2 knowledge bundle."""
    bundle_dir = tmp_path / "knowledge"
    bundle_dir.mkdir()

    # Root index catalog
    (bundle_dir / "index.md").write_text("# Knowledge Catalog", encoding="utf-8")

    # Concept 1: Constraint convention with stale date in past
    conv_dir = bundle_dir / "conventions"
    conv_dir.mkdir()
    (conv_dir / "api-auth.md").write_text(
        """---
type: rule
title: API Auth Standard
description: Mandatory token auth for external endpoints
governance: constraint
status: stable
stale_after: 2026-01-01
code_refs:
  - src/api/v1/**
tags:
  - auth
  - security
generated:
  by: agent/myrm-v1
  at: "2026-09-02T12:00:00Z"
verified:
  - by: human/alice
    at: "2026-09-01T10:00:00Z"
---
# API Auth Standard Body
Every endpoint requires valid cryptographic signature.
""",
        encoding="utf-8",
    )

    # Concept 2: Context architecture note
    (bundle_dir / "database-choice.md").write_text(
        """---
type: architecture
title: Database Selection
description: Embedded SQLite chosen for local isolation
governance: context
status: stable
stale_after: 2026-12-31
tags:
  - sqlite
  - storage
generated:
  by: human/bob
  at: "2026-10-01T08:00:00Z"
---
# Database Architecture
Local embedded database eliminates cloud dependencies.
""",
        encoding="utf-8",
    )

    return bundle_dir


@pytest.fixture
def isolated_service() -> GitOKFService:
    """Provides an isolated GitOKFService instance."""
    return GitOKFService()


@pytest.fixture
def test_app(isolated_service: GitOKFService) -> FastAPI:
    """Creates a FastAPI test application with dependency overrides."""
    app = FastAPI()
    app.include_router(git_okf_router, prefix="/api/memory")
    app.dependency_overrides[get_git_okf_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_bundle_load_and_bm25_search_api(
    test_app: FastAPI,
    sample_bundle_dir: Path,
) -> None:
    """Verifies loading OKF bundle and performing sub-millisecond lexical search."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Load bundle from filesystem
        res_load = await client.post(
            "/api/memory/git-okf/bundle/load",
            json={"bundle_path": str(sample_bundle_dir)},
        )
        assert res_load.status_code == 200
        data_load = res_load.json()
        assert data_load["is_success"] is True
        assert data_load["loaded_concepts_count"] == 2

        # 2. Search by keyword
        res_search = await client.post(
            "/api/memory/git-okf/concepts/search",
            json={"query": "token authentication signature", "limit": 5},
        )
        assert res_search.status_code == 200
        hits = res_search.json()
        assert len(hits) >= 1
        assert hits[0]["concept_id"] == "conventions/api-auth"
        assert hits[0]["governance"] == "constraint"
        assert hits[0]["is_stale"] is True  # expired on 2026-01-01

        # 3. Governance filter search
        res_filtered = await client.post(
            "/api/memory/git-okf/concepts/search",
            json={"query": "database", "filter_governance": "context"},
        )
        assert res_filtered.status_code == 200
        filtered_hits = res_filtered.json()
        assert len(filtered_hits) == 1
        assert filtered_hits[0]["concept_id"] == "database-choice"


@pytest.mark.asyncio
async def test_bundle_validation_and_progressive_disclosure_api(
    test_app: FastAPI,
    sample_bundle_dir: Path,
) -> None:
    """Verifies rot validation, anti-tamper detection, and progressive disclosure endpoints."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Load bundle first
        await client.post(
            "/api/memory/git-okf/bundle/load",
            json={"bundle_path": str(sample_bundle_dir)},
        )

        # 2. Conformance and anti-tamper audit
        res_val = await client.post("/api/memory/git-okf/validate")
        assert res_val.status_code == 200
        val_data = res_val.json()
        assert val_data["is_conformant"] is True
        assert val_data["stale_count"] == 1  # api-auth is expired
        # Human verification predates agent generation -> superseded trust violation
        assert val_data["superseded_trust_count"] == 1
        assert val_data["gate_passed"] is False

        # 3. Phase 1: Progressive disclosure card summary (<300 tokens footprint)
        res_summary = await client.get("/api/memory/git-okf/disclosure/summary")
        assert res_summary.status_code == 200
        summary_data = res_summary.json()
        assert summary_data["total_concepts"] == 2
        assert summary_data["stale_count"] == 1
        assert len(summary_data["concepts"]) == 2

        # 4. Phase 2: On-demand concept detailed card
        res_detail = await client.get("/api/memory/git-okf/concepts/conventions/api-auth")
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["id"] == "conventions/api-auth"
        assert "cryptographic signature" in detail_data["body"]
        assert detail_data["is_stale"] is True
