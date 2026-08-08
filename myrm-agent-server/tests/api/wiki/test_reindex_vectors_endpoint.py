"""Unit tests for POST /wiki/reindex-vectors response mapping."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.retrieval.reindex_vectors import WikiVectorReindexResult

from app.core.security.auth.identity import LOCAL_USER_ID


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    from tests.support.minimal_app import build_minimal_app

    return TestClient(build_minimal_app(preset="wiki"))


@pytest.fixture
def mock_archiver() -> MagicMock:
    archiver = MagicMock()
    archiver._structure = MagicMock()
    archiver._query_engine = MagicMock()
    archiver._query_engine._indexer = MagicMock()
    archiver._asset_indexer = MagicMock()
    return archiver


def test_reindex_vectors_success_response(
    client: TestClient,
    mock_archiver: MagicMock,
) -> None:
    from app.api.wiki.router import _get_wiki_archiver

    result = WikiVectorReindexResult(
        concepts_scanned=4,
        concepts_reindexed=2,
        skipped_drafts=1,
        sidecars_reindexed=1,
        assets_indexed=3,
        assets_failed=0,
        failed=0,
        errors=(),
    )

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        with (
            patch(
                "app.services.wiki.asset_index_service.ensure_archiver_asset_indexer",
                new=AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.retrieval.reindex_vectors.reindex_published_vectors",
                new=AsyncMock(return_value=result),
            ) as reindex_mock,
            patch(
                "app.api.wiki.router._after_wiki_vault_mutation",
                new=AsyncMock(),
            ) as after_mutation_mock,
            patch(
                "app.services.wiki.ingest_events.publish_wiki_ingest_snapshot",
                new=AsyncMock(),
            ),
        ):
            response = client.post("/api/v1/wiki/reindex-vectors")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["scanned"] == 4
        assert data["reindexed"] == 6
        assert data["concepts_reindexed"] == 2
        assert data["sidecars_reindexed"] == 1
        assert data["assets_indexed"] == 3
        assert data["skipped_drafts"] == 1
        assert data["failed"] == 0
        assert data["errors"] == []
        assert "2 concepts" in data["message"]
        assert "1 sidecars" in data["message"]
        assert "3 assets" in data["message"]
        assert "1 drafts skipped" in data["message"]
        reindex_mock.assert_awaited_once()
        after_mutation_mock.assert_awaited_once()
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)


def test_reindex_vectors_partial_failure_response(
    client: TestClient,
    mock_archiver: MagicMock,
) -> None:
    from app.api.wiki.router import _get_wiki_archiver

    result = WikiVectorReindexResult(
        concepts_scanned=2,
        concepts_reindexed=1,
        skipped_drafts=0,
        sidecars_reindexed=0,
        assets_indexed=0,
        assets_failed=0,
        failed=1,
        errors=("concept:big-note: embed window exceeded",),
    )

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        with (
            patch(
                "app.services.wiki.asset_index_service.ensure_archiver_asset_indexer",
                new=AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.retrieval.reindex_vectors.reindex_published_vectors",
                new=AsyncMock(return_value=result),
            ),
            patch(
                "app.api.wiki.router._after_wiki_vault_mutation",
                new=AsyncMock(),
            ) as after_mutation_mock,
            patch(
                "app.services.wiki.ingest_events.publish_wiki_ingest_snapshot",
                new=AsyncMock(),
            ),
        ):
            response = client.post("/api/v1/wiki/reindex-vectors")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["failed"] == 1
        assert data["errors"] == ["concept:big-note: embed window exceeded"]
        assert "1 failed" in data["message"]
        after_mutation_mock.assert_awaited_once()
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)
