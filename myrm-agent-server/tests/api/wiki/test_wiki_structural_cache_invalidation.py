"""Router hooks must invalidate structural lint TTL cache after vault mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID
from myrm_agent_harness.toolkits.wiki.pipeline.apply.types import WikiApplyOp, WikiApplyResult


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@dataclass(frozen=True, slots=True)
class _RepairTypesResult:
    files_scanned: int = 3
    files_repaired: int = 2
    files_skipped: int = 0
    errors: list[str] = field(default_factory=list)


@pytest.fixture
def client() -> TestClient:
    from tests.support.minimal_app import build_minimal_app

    return TestClient(build_minimal_app(preset="wiki"))


@pytest.fixture(autouse=True)
def _bypass_auth():
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


def test_repair_types_invalidates_structural_cache(client: TestClient) -> None:
    with patch(
        "app.api.wiki.router._invalidate_wiki_structural_stats_cache",
    ) as invalidate_mock, patch(
        "myrm_agent_harness.toolkits.wiki.core.frontmatter_contract.repair_missing_types",
        return_value=_RepairTypesResult(),
    ):
        response = client.post("/api/v1/wiki/repair-types")

    assert response.status_code == 200
    invalidate_mock.assert_called_once()


def test_repair_types_skips_invalidate_when_nothing_repaired(client: TestClient) -> None:
    with patch(
        "app.api.wiki.router._invalidate_wiki_structural_stats_cache",
    ) as invalidate_mock, patch(
        "myrm_agent_harness.toolkits.wiki.core.frontmatter_contract.repair_missing_types",
        return_value=_RepairTypesResult(files_repaired=0),
    ):
        response = client.post("/api/v1/wiki/repair-types")

    assert response.status_code == 200
    invalidate_mock.assert_not_called()


def test_apply_invalidates_structural_cache(client: TestClient) -> None:
    apply_result = WikiApplyResult(
        success=True,
        op=WikiApplyOp.PATCH_COMPILED_TRUTH,
        concept_name="Gravity",
        message="ok",
        content_hash="abc",
    )
    with patch(
        "app.api.wiki.router._invalidate_wiki_structural_stats_cache",
    ) as invalidate_mock, patch(
        "myrm_agent_harness.toolkits.wiki.pipeline.apply.apply_wiki_mutation",
        new_callable=AsyncMock,
        return_value=apply_result,
    ):
        response = client.post(
            "/api/v1/wiki/apply",
            json={
                "op": "patch_compiled_truth",
                "concept_name": "Gravity",
                "compiled_truth": "Updated truth.",
            },
        )

    assert response.status_code == 200
    invalidate_mock.assert_called_once()


def test_delete_concept_invalidates_structural_cache() -> None:
    from tests.support.minimal_app import build_minimal_app

    from app.api.wiki.router import _get_wiki_archiver

    app = build_minimal_app(preset="wiki")
    mock_archiver = MagicMock()
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_archiver._structure.get_concept_file_path.return_value = mock_path
    mock_archiver._query_engine._indexer.delete = AsyncMock()

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    scoped_client = TestClient(app)
    try:
        with patch(
            "app.api.wiki.router._invalidate_wiki_structural_stats_cache",
        ) as invalidate_mock:
            response = scoped_client.delete("/api/v1/wiki/concepts/Gravity")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    invalidate_mock.assert_called_once()


def test_pending_approve_invalidates_structural_cache() -> None:
    from tests.support.minimal_app import build_minimal_app

    from app.api.wiki.router import _get_wiki_archiver

    app = build_minimal_app(preset="wiki")
    mock_archiver = MagicMock()
    mock_archiver._pending_mgr.approve_edit = AsyncMock(return_value=True)

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    scoped_client = TestClient(app)
    try:
        with patch(
            "app.api.wiki.router._invalidate_wiki_structural_stats_cache",
        ) as invalidate_mock, patch(
            "app.api.wiki.router._refresh_wiki_cognitive_map",
        ):
            response = scoped_client.post("/api/v1/wiki/pending/1/approve", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    invalidate_mock.assert_called_once()


def test_delete_folder_invalidates_structural_cache() -> None:
    from tests.support.minimal_app import build_minimal_app

    from app.api.wiki.router import _get_wiki_archiver

    app = build_minimal_app(preset="wiki")
    mock_archiver = MagicMock()
    mock_archiver._structure.delete_folder_safe = AsyncMock(return_value=3)

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    scoped_client = TestClient(app)
    try:
        with patch(
            "app.api.wiki.router._invalidate_wiki_structural_stats_cache",
        ) as invalidate_mock:
            response = scoped_client.delete("/api/v1/wiki/tree/folder?path=notes")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    invalidate_mock.assert_called_once()
