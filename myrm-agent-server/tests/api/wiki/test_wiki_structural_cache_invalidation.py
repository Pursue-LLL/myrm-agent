"""Router hooks must invalidate structural lint TTL cache after vault mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.pipeline.apply.types import WikiApplyOp, WikiApplyResult

from app.core.security.auth.identity import LOCAL_USER_ID


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


@dataclass(frozen=True, slots=True)
class _RepairPublicationResult:
    files_scanned: int = 5
    files_repaired: int = 2
    files_skipped: int = 0
    files_skipped_intentional_drafts: int = 0
    reindexed: int = 1
    errors: tuple[str, ...] = ()


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
    with (
        patch(
            "app.api.wiki.router._after_wiki_vault_mutation",
            new_callable=AsyncMock,
        ) as invalidate_mock,
        patch(
            "myrm_agent_harness.toolkits.wiki.core.frontmatter_contract.repair_missing_types",
            return_value=_RepairTypesResult(),
        ),
    ):
        response = client.post("/api/v1/wiki/repair-types")

    assert response.status_code == 200
    invalidate_mock.assert_called_once()


def test_repair_types_skips_invalidate_when_nothing_repaired(client: TestClient) -> None:
    with (
        patch(
            "app.api.wiki.router._after_wiki_vault_mutation",
            new_callable=AsyncMock,
        ) as invalidate_mock,
        patch(
            "myrm_agent_harness.toolkits.wiki.core.frontmatter_contract.repair_missing_types",
            return_value=_RepairTypesResult(files_repaired=0),
        ),
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
    with (
        patch(
            "app.api.wiki.router._after_wiki_vault_mutation",
            new_callable=AsyncMock,
        ) as invalidate_mock,
        patch(
            "myrm_agent_harness.toolkits.wiki.pipeline.apply.apply_wiki_mutation",
            new_callable=AsyncMock,
            return_value=apply_result,
        ),
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
    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

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
            "app.api.wiki.router._after_wiki_vault_mutation",
            new_callable=AsyncMock,
        ) as invalidate_mock:
            response = scoped_client.delete("/api/v1/wiki/concepts/Gravity")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    invalidate_mock.assert_called_once()


def test_pending_approve_invalidates_structural_cache() -> None:
    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")
    mock_archiver = MagicMock()
    mock_archiver._pending_mgr.approve_edit = AsyncMock(return_value=True)

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    scoped_client = TestClient(app)
    try:
        with (
            patch(
                "app.api.wiki.router._after_wiki_vault_mutation",
                new_callable=AsyncMock,
            ) as invalidate_mock,
            patch(
                "app.api.wiki.router._refresh_wiki_cognitive_map",
            ),
        ):
            response = scoped_client.post("/api/v1/wiki/pending/1/approve", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    invalidate_mock.assert_called_once()


def test_delete_folder_invalidates_structural_cache() -> None:
    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")
    mock_archiver = MagicMock()
    mock_archiver._structure.delete_folder_safe = AsyncMock(return_value=3)

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    scoped_client = TestClient(app)
    try:
        with patch(
            "app.api.wiki.router._after_wiki_vault_mutation",
            new_callable=AsyncMock,
        ) as invalidate_mock:
            response = scoped_client.delete("/api/v1/wiki/tree/folder?path=notes")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    invalidate_mock.assert_called_once()


def test_move_invalidates_structural_cache(tmp_path) -> None:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    structure = WikiStructure(tmp_path / "vault")
    structure.ensure_structure()
    concept_path = structure.get_concept_file_path("Physics/Gravity")
    concept_path.write_text("---\ntype: concept\n---\n\n# Gravity\n", encoding="utf-8")

    mock_archiver = MagicMock()
    mock_archiver._structure = structure
    mock_archiver._query_engine._indexer = MagicMock()

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    scoped_client = TestClient(app)
    try:
        with (
            patch(
                "app.api.wiki.router._after_wiki_vault_mutation",
                new_callable=AsyncMock,
            ) as invalidate_mock,
            patch(
                "myrm_agent_harness.toolkits.wiki.pipeline.publication.reindex_concepts_after_move",
                new_callable=AsyncMock,
            ),
        ):
            response = scoped_client.put(
                "/api/v1/wiki/tree/move",
                json={
                    "source_path": "Physics/Gravity",
                    "target_path": "Physics/Gravitation",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    invalidate_mock.assert_called_once()
    assert invalidate_mock.await_args.args[1] == "move concept"


def test_repair_publication_invalidates_structural_cache(client: TestClient) -> None:
    with (
        patch(
            "app.api.wiki.router._after_wiki_vault_mutation",
            new_callable=AsyncMock,
        ) as invalidate_mock,
        patch(
            "myrm_agent_harness.toolkits.wiki.pipeline.publication.repair_publication_status",
            new_callable=AsyncMock,
            return_value=_RepairPublicationResult(),
        ),
        patch(
            "app.api.wiki.router._refresh_wiki_cognitive_map",
        ),
    ):
        response = client.post("/api/v1/wiki/repair-publication")

    assert response.status_code == 200
    invalidate_mock.assert_called_once()
    assert invalidate_mock.await_args.args[1] == "repair publication status"


def test_repair_publication_skips_invalidate_when_nothing_changed(client: TestClient) -> None:
    with (
        patch(
            "app.api.wiki.router._after_wiki_vault_mutation",
            new_callable=AsyncMock,
        ) as invalidate_mock,
        patch(
            "myrm_agent_harness.toolkits.wiki.pipeline.publication.repair_publication_status",
            new_callable=AsyncMock,
            return_value=_RepairPublicationResult(
                files_scanned=3,
                files_repaired=0,
                files_skipped=3,
                reindexed=0,
            ),
        ),
    ):
        response = client.post("/api/v1/wiki/repair-publication")

    assert response.status_code == 200
    invalidate_mock.assert_not_called()
