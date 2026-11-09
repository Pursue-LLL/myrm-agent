"""Contract tests for the consolidation undo endpoints of the Memory Command Center."""

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import UndoResult, UndoSummary

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app

URL = "/api/v1/memory/command-center/consolidation/undo"
HARNESS = "app.api.memory.operations.command_center_consolidation"
SUMMARY = UndoSummary(
    cycle_id="cycle-1",
    recorded_at=datetime(2026, 11, 9, 8, 30, tzinfo=UTC),
    merged=2,
    corrected=1,
    updated=3,
    change_count=9,
    conflict_count=1,
)

app = build_minimal_app(preset="memory")


@pytest.fixture
def manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(manager: MagicMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    app.dependency_overrides[get_crud_memory_manager] = lambda: manager
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield TestClient(app)
    app.dependency_overrides.pop(get_deploy_identity, None)
    app.dependency_overrides.pop(get_crud_memory_manager, None)


def test_the_undoable_cycle_is_described_with_what_it_did_and_what_changed_since(client: TestClient, manager: MagicMock) -> None:
    with patch(f"{HARNESS}.get_undo_summary", new=AsyncMock(return_value=SUMMARY)) as describe:
        response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "summary": {
            "cycle_id": "cycle-1",
            "recorded_at": "2026-11-09T08:30:00Z",
            "merged": 2,
            "corrected": 1,
            "updated": 3,
            "change_count": 9,
            "conflict_count": 1,
        }
    }
    describe.assert_awaited_once_with(manager)


def test_nothing_to_undo_is_an_object_with_a_null_summary_not_a_bare_null(client: TestClient) -> None:
    with patch(f"{HARNESS}.get_undo_summary", new=AsyncMock(return_value=None)):
        response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"summary": None}


def test_undoing_passes_the_shown_cycle_through_and_reports_what_was_restored(client: TestClient, manager: MagicMock) -> None:
    result = UndoResult(rolled_back=8, skipped_conflict=1, errors=0)
    with patch(f"{HARNESS}.undo_last_consolidation", new=AsyncMock(return_value=result)) as undo:
        response = client.post(URL, json={"cycle_id": "cycle-1"})

    assert response.status_code == 200
    assert response.json() == {"rolled_back": 8, "skipped_conflict": 1, "errors": 0}
    undo.assert_awaited_once_with(manager, "cycle-1")


def test_a_cycle_that_is_gone_or_replaced_is_a_conflict(client: TestClient) -> None:
    with patch(f"{HARNESS}.undo_last_consolidation", new=AsyncMock(return_value=None)):
        response = client.post(URL, json={"cycle_id": "stale"})

    assert response.status_code == 409
    assert "can no longer be undone" in response.json()["detail"]


def test_undoing_without_naming_a_cycle_is_rejected(client: TestClient) -> None:
    response = client.post(URL, json={})

    assert response.status_code == 422
