"""Integration: POST /wiki/reindex-vectors full HTTP → harness SSOT wiring."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import WikiPublishStatus

from app.api.wiki.router import _get_wiki_archiver
from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.minimal_app import build_minimal_app


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


def _published_markdown(body: str) -> str:
    return f"---\npublish_status: published\n---\n\n## Compiled Truth\n{body}"


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def wiki_archiver(tmp_path: Path) -> MemoryToWikiArchiver:
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
    config = WikiConfig(
        enable_hybrid_search=False,
        enable_directory_sidecars=True,
        enable_asset_index=False,
    )
    return MemoryToWikiArchiver(
        mock_llm,
        wiki_dir=tmp_path / "wiki-vault",
        config=config,
    )


@pytest.fixture
def wiki_client(wiki_archiver: MemoryToWikiArchiver) -> Iterator[TestClient]:
    app = build_minimal_app(preset="wiki")
    app.dependency_overrides[_get_wiki_archiver] = lambda: wiki_archiver
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(_get_wiki_archiver, None)


@pytest.mark.integration
def test_reindex_vectors_http_success(
    wiki_archiver: MemoryToWikiArchiver,
    wiki_client: TestClient,
) -> None:
    structure = wiki_archiver._structure
    indexer = wiki_archiver._query_engine._indexer

    published_path = structure.get_concept_file_path("live-note")
    published_path.write_text(_published_markdown("Stale indexed truth"), encoding="utf-8")

    draft_path = structure.get_concept_file_path("draft-only")
    draft_path.write_text(
        f"---\npublish_status: {WikiPublishStatus.DRAFT.value}\n---\n\n## Compiled Truth\nDraft",
        encoding="utf-8",
    )

    engine_dir = structure.concepts_dir / "ops"
    engine_dir.mkdir(parents=True)
    (engine_dir / ".abstract.md").write_text("Ops sidecar stale", encoding="utf-8")

    published_path.write_text(_published_markdown("Fresh truth from reindex"), encoding="utf-8")
    (engine_dir / ".abstract.md").write_text("Ops sidecar fresh", encoding="utf-8")

    response = wiki_client.post("/api/v1/wiki/reindex-vectors")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["concepts_reindexed"] == 1
    assert data["skipped_drafts"] == 1
    assert data["sidecars_reindexed"] == 1
    assert data["failed"] == 0
    assert data["errors"] == []
    assert "1 concepts" in data["message"]
    assert "1 sidecars" in data["message"]
    assert "1 drafts skipped" in data["message"]

    truth = indexer.get_truth("live-note")
    assert truth is not None
    assert "Fresh truth from reindex" in truth


@pytest.mark.integration
def test_reindex_vectors_empty_vault_boundary(wiki_client: TestClient) -> None:
    response = wiki_client.post("/api/v1/wiki/reindex-vectors")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["concepts_reindexed"] == 0
    assert data["sidecars_reindexed"] == 0
    assert data["skipped_drafts"] == 0
    assert data["failed"] == 0
    assert data["errors"] == []
