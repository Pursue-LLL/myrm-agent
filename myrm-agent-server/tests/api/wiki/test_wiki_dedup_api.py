"""Wiki corpus dedup API tests."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth() -> None:
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")
    return TestClient(app)


def test_wiki_stats_includes_dedup_stats(client: TestClient) -> None:
    response = client.get("/api/v1/wiki/stats")
    assert response.status_code == 200
    data = response.json()
    assert "dedup_stats" in data
    dedup = data["dedup_stats"]
    assert isinstance(dedup["duplicate_groups_pending"], int)
    assert isinstance(dedup["blocks_compile"], bool)


def test_wiki_dedup_groups_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/wiki/dedup/groups")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_wiki_dedup_scan_endpoint_returns_202_accepted(client: TestClient) -> None:
    from app.services.wiki.dedup_runner import WikiDedupScanScheduleResult

    with patch(
        "app.services.wiki.dedup_runner.schedule_wiki_dedup_scan",
        new=AsyncMock(
            return_value=WikiDedupScanScheduleResult(accepted=True),
        ),
    ):
        response = client.post("/api/v1/wiki/dedup/scan")
    assert response.status_code == 202
    data = response.json()
    assert data["accepted"] is True
    assert data["skipped"] is False


def test_wiki_dedup_scan_endpoint_returns_409_when_compile_busy(
    client: TestClient,
) -> None:
    from app.services.wiki.dedup_runner import WikiDedupScanScheduleResult

    with patch(
        "app.services.wiki.dedup_runner.schedule_wiki_dedup_scan",
        new=AsyncMock(
            return_value=WikiDedupScanScheduleResult(
                accepted=False,
                skipped=True,
                skipped_reason="compile_in_progress",
            ),
        ),
    ):
        response = client.post("/api/v1/wiki/dedup/scan")
    assert response.status_code == 409


def test_wiki_dedup_progress_endpoint(client: TestClient) -> None:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
        ScanProgress,
    )

    with patch(
        "app.services.wiki.dedup_runner.get_wiki_dedup_progress",
        return_value=ScanProgress(
            phase="scanning", files_scanned=3, files_total=10, message="Scanning"
        ),
    ):
        response = client.get("/api/v1/wiki/dedup/progress")
    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == "scanning"
    assert data["files_scanned"] == 3


def test_wiki_compile_returns_409_when_dedup_blocks(client: TestClient) -> None:
    with patch(
        "app.services.wiki.dedup_runner.wiki_dedup_blocks_compile",
        return_value=True,
    ):
        response = client.post("/api/v1/wiki/compile")
    assert response.status_code == 409
    assert "Duplicate review required" in response.json()["detail"]


def test_wiki_dedup_vault_hygiene_endpoint(client: TestClient) -> None:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
        VaultHygieneSnapshot,
    )

    with patch(
        "app.services.wiki.dedup_runner.get_wiki_dedup_vault_hygiene",
        return_value=VaultHygieneSnapshot(trashed=(), excluded=()),
    ):
        response = client.get("/api/v1/wiki/dedup/vault-hygiene")
    assert response.status_code == 200
    data = response.json()
    assert data["trashed"] == []
    assert data["excluded"] == []


def test_wiki_dedup_restore_trash_endpoint(client: TestClient) -> None:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
        TrashedRawEntry,
    )

    with patch(
        "app.services.wiki.dedup_runner.restore_wiki_dedup_trashed",
        new=AsyncMock(
            return_value=TrashedRawEntry(
                relative_path="archive/dup.md",
                trash_relpath=".corpus_trash/20260101__archive__dup.md",
                content_hash="abc",
                created_at="2026-01-01T00:00:00+00:00",
            ),
        ),
    ):
        response = client.post(
            "/api/v1/wiki/dedup/trash/restore",
            json={"relative_path": "archive/dup.md"},
        )
    assert response.status_code == 200
    assert response.json()["relative_path"] == "archive/dup.md"


def test_wiki_dedup_undo_excluded_endpoint(client: TestClient) -> None:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
        ExcludedRawEntry,
    )

    with patch(
        "app.services.wiki.dedup_runner.undo_wiki_dedup_excluded",
        new=AsyncMock(
            return_value=ExcludedRawEntry(
                relative_path="archive/dup.md",
                reason="manual exclude",
                created_at="2026-01-01T00:00:00+00:00",
            ),
        ),
    ):
        response = client.post(
            "/api/v1/wiki/dedup/excluded/undo",
            json={"relative_path": "archive/dup.md"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["relative_path"] == "archive/dup.md"
    assert data["reason"] == "manual exclude"


def test_wiki_dedup_group_snippets_endpoint(client: TestClient) -> None:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
        DuplicateMemberSnippet,
    )

    with patch(
        "app.services.wiki.dedup_runner.get_wiki_dedup_group_snippets",
        return_value=(
            DuplicateMemberSnippet(relative_path="notes/a.md", snippet="Shared body"),
            DuplicateMemberSnippet(
                relative_path="backup/a-copy.md", snippet="Shared body"
            ),
        ),
    ):
        response = client.get("/api/v1/wiki/dedup/groups/7/snippets")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["snippet"] == "Shared body"


def test_wiki_dedup_disposition_dismiss_endpoint(client: TestClient) -> None:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
        DispositionAction,
        DispositionResult,
    )

    with patch(
        "app.services.wiki.dedup_runner.apply_wiki_dedup_disposition",
        new=AsyncMock(
            return_value=DispositionResult(
                group_id=7,
                action=DispositionAction.DISMISS,
                affected_paths=("notes/a.md", "backup/a-copy.md"),
            ),
        ),
    ):
        response = client.post(
            "/api/v1/wiki/dedup/groups/7/disposition",
            json={"action": "dismiss", "reason": ""},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["group_id"] == 7
    assert data["action"] == "dismiss"
    assert data["affected_paths"] == ["notes/a.md", "backup/a-copy.md"]
