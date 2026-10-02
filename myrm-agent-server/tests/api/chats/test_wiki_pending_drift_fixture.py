"""Tests for wiki pending drift Chrome E2E seed/cleanup fixture."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

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

    return TestClient(build_minimal_app("chats", "wiki"))


def _pending_stats(client: TestClient) -> dict[str, int]:
    response = client.get("/api/v1/wiki/pending?limit=1")
    assert response.status_code == 200
    return response.json()["stats"]


def _seed(client: TestClient, count: int) -> dict[str, object]:
    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        response = client.post(f"/api/v1/chats/test/seed-pending-drift-fixture?count={count}")
    assert response.status_code == 200
    return response.json()


def _cleanup(client: TestClient) -> dict[str, object]:
    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        response = client.post("/api/v1/chats/test/cleanup-pending-drift-fixture")
    assert response.status_code == 200
    return response.json()


def test_seed_stages_marker_drafts_on_real_writer_path(client: TestClient) -> None:
    try:
        seeded = _seed(client, 3)
        assert seeded["count"] == 3
        assert len(seeded["edit_ids"]) == 3
        concept_prefix = str(seeded["concept_prefix"])
        assert concept_prefix.startswith("e2e-pending-drift-")

        listing = client.get("/api/v1/wiki/pending?limit=50&offset=0")
        assert listing.status_code == 200
        body = listing.json()
        staged = [e for e in body["pending_edits"] if str(e["concept_name"]).startswith(concept_prefix)]
        assert len(staged) == 3
        assert body["stats"]["pending"] >= 3
    finally:
        _cleanup(client)


def test_cleanup_removes_marker_drafts_and_restores_stats(client: TestClient) -> None:
    base = _pending_stats(client)
    _seed(client, 3)
    cleaned = _cleanup(client)
    assert cleaned["deleted"] == 3
    assert _pending_stats(client) == base


def test_external_reject_drifts_stats_then_cleanup_restores(client: TestClient) -> None:
    base = _pending_stats(client)
    try:
        seeded = _seed(client, 2)
        edit_ids = list(seeded["edit_ids"])
        assert len(edit_ids) == 2

        rejected = client.post(f"/api/v1/wiki/pending/{edit_ids[0]}/reject")
        assert rejected.status_code == 200

        drifted = _pending_stats(client)
        assert drifted["pending"] == base["pending"] + 1
        assert drifted["rejected"] == base["rejected"] + 1

        cleaned = _cleanup(client)
        assert cleaned["deleted"] == 2
    finally:
        _cleanup(client)
    assert _pending_stats(client) == base
