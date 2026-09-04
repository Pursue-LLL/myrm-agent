"""Wiki apply API integration tests."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.api.wiki.test_wiki_api import _FakeIdentity


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

    return TestClient(build_minimal_app(preset="wiki"))


def test_wiki_apply_create_note_and_editor_sections(client: TestClient) -> None:
    create = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "integration/apply-note",
            "body": "Integration summary body",
            "metadata": {"source_chat": "chat-1"},
        },
    )
    assert create.status_code == 200, create.text
    payload = create.json()
    assert payload["created"] is True
    assert payload["op"] == "create_note"

    get_resp = client.get("/api/v1/wiki/concepts/integration/apply-note")
    assert get_resp.status_code == 200, get_resp.text
    concept = get_resp.json()
    assert concept["editor_sections"]["compiled_truth"] == "Integration summary body"
    assert concept["editor_sections"]["tags"] == []


def test_wiki_apply_chat_forbidden_create_note(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wiki/apply",
        params={"caller": "chat"},
        json={
            "op": "create_note",
            "concept_name": "integration/chat-note",
            "body": "Body",
        },
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "forbidden_for_caller"


def test_wiki_apply_patch_and_append_timeline(client: TestClient) -> None:
    create = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "integration/patch-note",
            "body": "Original truth",
        },
    )
    assert create.status_code == 200, create.text

    patch = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "patch_compiled_truth",
            "concept_name": "integration/patch-note",
            "compiled_truth": "Updated truth",
        },
    )
    assert patch.status_code == 200, patch.text

    append = client.post(
        "/api/v1/wiki/apply",
        params={"caller": "settings"},
        json={
            "op": "append_timeline",
            "concept_name": "integration/patch-note",
            "timeline_entry": "evidence added in test",
        },
    )
    assert append.status_code == 200, append.text
    assert append.json()["appended"] is True

    duplicate = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "append_timeline",
            "concept_name": "integration/patch-note",
            "timeline_entry": "evidence added in test",
        },
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["appended"] is False

    concept = client.get("/api/v1/wiki/concepts/integration/patch-note").json()
    assert concept["editor_sections"]["compiled_truth"] == "Updated truth"
    assert "evidence added in test" in concept["editor_sections"]["timeline"]


def test_wiki_apply_update_metadata_replaces_tags(client: TestClient) -> None:
    create = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "integration/meta-note",
            "body": "Meta body",
            "tags": ["keep-me"],
        },
    )
    assert create.status_code == 200, create.text

    update = client.post(
        "/api/v1/wiki/apply",
        params={"caller": "settings"},
        json={
            "op": "update_metadata",
            "concept_name": "integration/meta-note",
            "tags": ["only-this"],
            "aliases": ["Alias One"],
        },
    )
    assert update.status_code == 200, update.text

    concept = client.get("/api/v1/wiki/concepts/integration/meta-note").json()
    assert concept["editor_sections"]["tags"] == ["only-this"]
    assert concept["editor_sections"]["aliases"] == ["Alias One"]


def test_wiki_apply_agent_forbidden_full_replace(client: TestClient) -> None:
    create = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "integration/forbidden-note",
            "body": "Body",
        },
    )
    assert create.status_code == 200, create.text

    response = client.post(
        "/api/v1/wiki/apply",
        params={"caller": "agent"},
        json={
            "op": "replace_full_document",
            "concept_name": "integration/forbidden-note",
            "content": "---\ntype: concept\n---\n## Compiled Truth\nx\n## Timeline\n- y\n",
        },
    )
    assert response.status_code == 403, response.text


def test_wiki_concept_get_returns_content_hash(client: TestClient) -> None:
    create = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "integration/hash-note",
            "body": "Hash body",
        },
    )
    assert create.status_code == 200, create.text
    assert create.json()["content_hash"]

    get_resp = client.get("/api/v1/wiki/concepts/integration/hash-note")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["content_hash"]


def test_wiki_apply_chat_forbidden_full_replace(client: TestClient) -> None:
    create = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "integration/chat-forbidden",
            "body": "Body",
        },
    )
    assert create.status_code == 200, create.text

    response = client.post(
        "/api/v1/wiki/apply",
        params={"caller": "chat"},
        json={
            "op": "replace_full_document",
            "concept_name": "integration/chat-forbidden",
            "content": "---\ntype: concept\n---\n## Compiled Truth\nx\n## Timeline\n- y\n",
        },
    )
    assert response.status_code == 403, response.text


def test_wiki_apply_if_match_conflict(client: TestClient) -> None:
    create = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "integration/lease-note",
            "body": "Lease body",
        },
    )
    assert create.status_code == 200, create.text

    conflict = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "patch_compiled_truth",
            "concept_name": "integration/lease-note",
            "compiled_truth": "Updated",
            "if_match": "deadbeef",
        },
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "conflict"


def test_wiki_apply_create_note_conflict(client: TestClient) -> None:
    payload = {
        "op": "create_note",
        "concept_name": "integration/conflict-note",
        "body": "First",
    }
    first = client.post("/api/v1/wiki/apply", json=payload)
    assert first.status_code == 200, first.text

    second = client.post("/api/v1/wiki/apply", json=payload)
    assert second.status_code == 409, second.text


def test_wiki_heal_claims_governance_endpoint(client: TestClient) -> None:
    create = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "integration/heal-note",
            "body": "Note body for claim healing",
        },
    )
    assert create.status_code == 200, create.text

    heal_resp = client.post(
        "/api/v1/wiki/governance/claims/heal",
        json={
            "concept_names": ["integration/heal-note"],
        },
    )
    assert heal_resp.status_code == 200, heal_resp.text
    data = heal_resp.json()
    assert data["success"] is True
    assert "total_healed_evidence" in data

