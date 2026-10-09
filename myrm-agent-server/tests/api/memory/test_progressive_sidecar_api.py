"""[POS]: tests/api/memory/test_progressive_sidecar_api.py
[INPUT]: FastAPI TestClient, isolated VFS instance, and progressive sidecar endpoints.
[OUTPUT]: Pytest integration tests verifying L0/L1/L2 bundle generation, sidecar persistence, and tiered reads.
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import ContextVirtualFileSystem

from app.api.memory.progressive_sidecar_router import (
    router as sidecar_router,
)
from app.services.memory.cvfs import get_context_vfs
from app.services.memory.progressive_sidecar_service import (
    ProgressiveSidecarService,
    get_progressive_sidecar_service,
)

SAMPLE_DOC = """# Security Governance Architecture Blueprint

This document sets the mandatory criteria for enterprise sovereign memory boundaries.
All components must adhere to strict zero-leakage protocols and deterministic auditing.

## 1. Zero Trust Principles
- **Egress Hardening**: Outbound connections must transit through audited gateway proxies.
- **Sidecar Isolation**: Summaries and metadata must never leak raw tokens before authentication.
- **Continuous Validation**: Token lifetimes must be cryptographically bounded and ephemeral.

## 2. Component Interface
```python
class SovereignGateway:
    def verify_attestation(self, token: str) -> bool:
        return True

    def rotate_session_key(self, session_id: str) -> str:
        return "rotated_key"
```

## 3. Operational Protocols
The system automatically purges expired tokens and writes audit entries to immutable storage.
Any unauthorized traversal attempts result in instant socket termination and incident reporting.

## 4. Threat Model and Mitigation Matrix
Adversarial prompt injection attacks are screened through bilateral lexical filters.
Sidecar extraction processes strictly strip internal reasoning blocks before persisting to disk.
"""


@pytest.fixture
def isolated_vfs() -> ContextVirtualFileSystem:
    """Create in-memory ContextVirtualFileSystem."""
    return ContextVirtualFileSystem(db_path=":memory:")


@pytest.fixture
def isolated_service(isolated_vfs: ContextVirtualFileSystem) -> ProgressiveSidecarService:
    """Create ProgressiveSidecarService backed by isolated VFS."""
    return ProgressiveSidecarService(vfs=isolated_vfs)


@pytest.fixture
def test_app(isolated_vfs: ContextVirtualFileSystem, isolated_service: ProgressiveSidecarService) -> FastAPI:
    """Create test FastAPI application with injected dependencies."""
    app = FastAPI()
    app.include_router(sidecar_router, prefix="/api/memory")
    app.dependency_overrides[get_context_vfs] = lambda: isolated_vfs
    app.dependency_overrides[get_progressive_sidecar_service] = lambda: isolated_service
    return app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_generate_bundle_api(client: AsyncClient) -> None:
    """Verify in-memory generation of three-tier progressive sidecar bundle."""
    payload = {
        "uri": "context://resources/sec_blueprint.md",
        "content": SAMPLE_DOC,
        "title": "Security Blueprint",
    }
    resp = await client.post("/api/memory/progressive-sidecar/generate-bundle", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["doc_id"] == "context://resources/sec_blueprint.md"
    assert "This document sets the mandatory criteria" in data["l0_abstract"]
    assert "## 1. Zero Trust Principles" in data["l1_overview"]
    assert data["l2_detail"] == SAMPLE_DOC
    assert len(data["frontmatter"]["digest_sha256"]) == 64
    assert data["token_savings_pct"] > 50.0


@pytest.mark.asyncio
async def test_write_with_sidecars_and_read_tiered_api(client: AsyncClient) -> None:
    """Verify persisting document with companion sidecars and reading across L0/L1/L2 tiers."""
    doc_uri = "context://resources/governance_adr.md"
    write_payload = {
        "uri": doc_uri,
        "content": SAMPLE_DOC,
        "title": "Governance ADR",
        "metadata": {"team": "secops"},
    }
    write_resp = await client.post("/api/memory/progressive-sidecar/write-with-sidecars", json=write_payload)
    assert write_resp.status_code == 200
    assert write_resp.json()["doc_id"] == doc_uri

    # 1. Read L0 Abstract
    read_l0_resp = await client.post(
        "/api/memory/progressive-sidecar/read-tiered",
        json={"uri": doc_uri, "tier": "l0_abstract"},
    )
    assert read_l0_resp.status_code == 200
    l0_data = read_l0_resp.json()
    assert l0_data["tier"] == "l0_abstract"
    assert l0_data["has_higher_detail"] is True
    assert "This document sets" in l0_data["content"]
    assert l0_data["token_est"] < 120

    # 2. Read L1 Overview
    read_l1_resp = await client.post(
        "/api/memory/progressive-sidecar/read-tiered",
        json={"uri": doc_uri, "tier": "l1_overview"},
    )
    assert read_l1_resp.status_code == 200
    l1_data = read_l1_resp.json()
    assert l1_data["tier"] == "l1_overview"
    assert l1_data["has_higher_detail"] is True
    assert "class SovereignGateway:" in l1_data["content"]

    # 3. Read L2 Full Detail
    read_l2_resp = await client.post(
        "/api/memory/progressive-sidecar/read-tiered",
        json={"uri": doc_uri, "tier": "l2_detail"},
    )
    assert read_l2_resp.status_code == 200
    l2_data = read_l2_resp.json()
    assert l2_data["tier"] == "l2_detail"
    assert l2_data["has_higher_detail"] is False
    assert l2_data["content"] == SAMPLE_DOC


@pytest.mark.asyncio
async def test_read_tiered_nonexistent_returns_404(client: AsyncClient) -> None:
    """Verify reading non-existent document returns HTTP 404."""
    resp = await client.post(
        "/api/memory/progressive-sidecar/read-tiered",
        json={"uri": "context://resources/missing.md", "tier": "l0_abstract"},
    )
    assert resp.status_code == 404
