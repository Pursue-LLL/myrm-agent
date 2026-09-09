"""Integration tests for wiki tree move, canonical ID pinning, alias redirection, and link refactoring.

Tests the real API pipeline end-to-end via /api/v1/wiki/tree/move.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.api.wiki.test_wiki_api import _FakeIdentity


@pytest.fixture(autouse=True)
def _bypass_auth() -> None:
    """Bypass auth so all requests act as authenticated user."""
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    """Create minimal test client with wiki preset."""
    from tests.support.minimal_app import build_minimal_app

    return TestClient(build_minimal_app(preset="wiki"))


def test_wiki_tree_move_canonical_id_aliases_and_anchored_links(client: TestClient) -> None:
    """Verify wiki tree move end-to-end:

    1. Creates target note and referrer note with both [markdown link#anchor] and [[wikilink]].
    2. Moves target note to a new directory via PUT /api/v1/wiki/tree/move.
    3. Verifies canonical_id pinning, supersedes, and aliases in target note frontmatter.
    4. Verifies referrer note links are rewritten without losing URL fragments/anchors.
    5. Verifies old concept path returns 404 while new concept path returns 200.
    """
    # 1. Create target note (source of move)
    body_b = "## architecture-decisions\nCritical service architecture decisions.\n"
    res_b = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "engineering/service-b",
            "body": body_b,
        },
    )
    assert res_b.status_code == 200, res_b.text

    # 2. Create referrer note linking to service-b with markdown anchor link and wikilink
    body_a = (
        "## Overview\n"
        "Reference: [Service Decisions](../engineering/service-b.md#architecture-decisions)\n"
        "And wikilink: [[service-b]]\n"
    )
    res_a = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "architecture/system-overview-a",
            "body": body_a,
        },
    )
    assert res_a.status_code == 200, res_a.text

    # 3. Perform move via PUT /api/v1/wiki/tree/move
    move_resp = client.put(
        "/api/v1/wiki/tree/move",
        json={
            "source_path": "engineering/service-b",
            "target_path": "core/services/service-b-renamed",
        },
    )
    assert move_resp.status_code == 200, move_resp.text
    move_data = move_resp.json()
    assert move_data["success"] is True

    # 4. Verify new concept exists and has canonical_id, supersedes, and aliases
    get_new = client.get("/api/v1/wiki/concepts/core/services/service-b-renamed")
    assert get_new.status_code == 200, get_new.text
    new_concept_data = get_new.json()

    # Frontmatter metadata verification from concept content
    from myrm_agent_harness.utils.markdown_frontmatter import parse_frontmatter

    metadata, _ = parse_frontmatter(new_concept_data["content"])
    assert metadata.get("canonical_id") == "engineering.service-b"
    assert "engineering/service-b" in metadata.get("supersedes", [])
    aliases = metadata.get("aliases", [])
    assert "engineering/service-b" in aliases

    # 5. Verify referrer note links rewritten with anchor preserved
    get_ref = client.get("/api/v1/wiki/concepts/architecture/system-overview-a")
    assert get_ref.status_code == 200, get_ref.text
    ref_body = get_ref.json()["editor_sections"]["compiled_truth"]

    # Markdown link must point to new relative path AND keep #architecture-decisions anchor
    assert "../core/services/service-b-renamed.md#architecture-decisions" in ref_body
    # Wikilink must point to new slug
    assert "[[core/services/service-b-renamed]]" in ref_body

    # 6. Verify old concept path is 404
    get_old = client.get("/api/v1/wiki/concepts/engineering/service-b")
    assert get_old.status_code == 404
