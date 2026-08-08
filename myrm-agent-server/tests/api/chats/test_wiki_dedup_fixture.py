"""Tests for wiki dedup Chrome E2E seed fixture."""

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


def test_seed_wiki_dedup_fixture_creates_open_group(client: TestClient) -> None:
    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        response = client.post("/api/v1/chats/test/seed-wiki-dedup-fixture")
    assert response.status_code == 200
    data = response.json()
    assert data["open_groups"] >= 1
    assert data["exact_groups"] >= 1
    assert data["ui_path"] == "/settings/wiki?wikiTab=duplicateReview"


def test_seed_wiki_dedup_fixture_dismiss_then_resurface_on_new_member(
    client: TestClient,
) -> None:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
        CorpusDedupScanner,
        GroupStatus,
    )

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        seed = client.post("/api/v1/chats/test/seed-wiki-dedup-fixture")
    assert seed.status_code == 200
    group_id = int(seed.json()["group_ids"][0])

    groups_before = client.get("/api/v1/wiki/dedup/groups")
    assert groups_before.status_code == 200
    target_group = next(
        group for group in groups_before.json() if group["group_id"] == group_id
    )
    member_paths = target_group["members"]
    assert len(member_paths) >= 2

    dismiss = client.post(
        f"/api/v1/wiki/dedup/groups/{group_id}/disposition",
        json={"action": "dismiss", "reason": ""},
    )
    assert dismiss.status_code == 200

    groups_after_dismiss = client.get("/api/v1/wiki/dedup/groups")
    assert groups_after_dismiss.status_code == 200
    open_or_deferred = [
        group
        for group in groups_after_dismiss.json()
        if group["status"] in {"open", "deferred"}
    ]
    assert open_or_deferred == []

    from app.services.wiki.vault import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=None)
    structure = archiver._structure
    sample_path = member_paths[0]["relative_path"]
    folder = sample_path.rsplit("/", 1)[0]
    suffix = sample_path.rsplit("-", 1)[-1].removesuffix(".md")
    new_path = structure.get_raw_file_path(f"{folder}/c-{suffix}.md")
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(
        "# Wiki dedup E2E fixture\n\nShared duplicate body for Chrome E2E.",
        encoding="utf-8",
    )

    new_rel = new_path.relative_to(structure.raw_dir).as_posix()
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    open_groups = scanner.store.list_groups(status=GroupStatus.OPEN)
    assert len(open_groups) >= 1
    resurfaced = next(
        group
        for group in open_groups
        if any(member.relative_path == new_rel for member in group.members)
    )
    assert len(resurfaced.members) >= len(member_paths) + 1
