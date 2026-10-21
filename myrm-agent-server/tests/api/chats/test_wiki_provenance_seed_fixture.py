"""Tests for wiki provenance gap Chrome E2E seed fixture."""

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


def test_seed_wiki_provenance_gap_fixture_creates_lint_issue(
    client: TestClient,
) -> None:
    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        seed = client.post("/api/v1/chats/test/seed-wiki-provenance-gap-fixture")
    assert seed.status_code == 200, seed.text
    payload = seed.json()
    assert payload.get("concept_relative_path")
    assert int(payload.get("provenance_gaps") or 0) >= 1

    health = client.get("/api/v1/wiki/health-report")
    assert health.status_code == 200, health.text
    issues = health.json().get("issues") or []
    assert any(item.get("issue_type") == "provenance_gap" for item in issues)
