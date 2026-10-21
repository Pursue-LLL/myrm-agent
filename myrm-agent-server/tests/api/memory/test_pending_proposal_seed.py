"""HTTP tests for the local-only pending-proposal Chrome E2E seed endpoint."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, PendingResolutionAction, SemanticMemory

from tests.support.minimal_app import build_minimal_app

_SEED_URL = "/api/v1/memory/test/seed-pending-proposal"
_TARGET = SemanticMemory(id="mem-old", content="User works at ByteDance")

app = build_minimal_app(preset="memory")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def manager() -> Iterator[MagicMock]:
    """Local-mode seed route backed by a fake memory manager."""
    fake = MagicMock()
    fake.get_memory = AsyncMock(return_value=_TARGET)
    fake.submit_pending = AsyncMock(return_value="pending-1")
    with (
        patch("app.api.memory.test_seed.is_local_mode", return_value=True),
        patch("app.api.memory.test_seed._create_seed_manager", new=AsyncMock(return_value=fake)),
    ):
        yield fake


@pytest.mark.parametrize(
    ("action", "expected"),
    [("correct", PendingResolutionAction.CORRECT), ("delete", PendingResolutionAction.DELETE)],
)
def test_seed_queues_proposal_with_target_content(
    client: TestClient, manager: MagicMock, action: str, expected: PendingResolutionAction
) -> None:
    resp = client.post(
        _SEED_URL,
        json={"content": "User now works at Google", "resolution_action": action, "target_memory_id": "mem-old"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"pending_id": "pending-1"}
    manager.get_memory.assert_awaited_once_with("mem-old")
    submitted = manager.submit_pending.await_args
    assert submitted.args[0].content == "User now works at Google"
    assert submitted.kwargs == {
        "resolution_action": expected,
        "target_memory_id": "mem-old",
        "target_content": "User works at ByteDance",
    }


@pytest.mark.parametrize("target", [None, EpisodicMemory(id="mem-event", content="User attended a conference")])
def test_seed_rejects_unknown_or_non_semantic_target(
    client: TestClient, manager: MagicMock, target: EpisodicMemory | None
) -> None:
    manager.get_memory.return_value = target

    resp = client.post(
        _SEED_URL,
        json={"content": "x", "resolution_action": "delete", "target_memory_id": "missing"},
    )

    assert resp.status_code == 404
    manager.submit_pending.assert_not_awaited()


def test_seed_reports_duplicate_proposal(client: TestClient, manager: MagicMock) -> None:
    manager.submit_pending.return_value = ""

    resp = client.post(
        _SEED_URL,
        json={"content": "x", "resolution_action": "correct", "target_memory_id": "mem-old"},
    )

    assert resp.status_code == 409


def test_seed_only_accepts_destructive_resolution_actions(client: TestClient, manager: MagicMock) -> None:
    resp = client.post(
        _SEED_URL,
        json={"content": "x", "resolution_action": "store", "target_memory_id": "mem-old"},
    )

    assert resp.status_code == 422
    manager.submit_pending.assert_not_awaited()


def test_seed_hidden_outside_local_mode(client: TestClient) -> None:
    with patch("app.api.memory.test_seed.is_local_mode", return_value=False):
        resp = client.post(
            _SEED_URL,
            json={"content": "x", "resolution_action": "correct", "target_memory_id": "mem-old"},
        )

    assert resp.status_code == 404
