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


def test_wiki_tree_move_directory_recursive_batch_redirect(client: TestClient) -> None:
    """Verify recursive directory move:
    
    1. Creates nested notes under a directory folder.
    2. Moves the entire folder via PUT /api/v1/wiki/tree/move.
    3. Verifies all nested notes have canonical_id and aliases injected.
    4. Verifies external referrer note links are rewritten for all nested notes.
    """
    # Create nested notes
    res1 = client.post(
        "/api/v1/wiki/apply",
        json={"op": "create_note", "concept_name": "folder-src/sub/doc-alpha", "body": "Alpha body"},
    )
    assert res1.status_code == 200, res1.text

    res2 = client.post(
        "/api/v1/wiki/apply",
        json={"op": "create_note", "concept_name": "folder-src/sub/doc-beta", "body": "Beta body"},
    )
    assert res2.status_code == 200, res2.text

    # External referrer linking to both
    ref_body = "See [[folder-src/sub/doc-alpha]] and [[folder-src/sub/doc-beta]]"
    res_ref = client.post(
        "/api/v1/wiki/apply",
        json={"op": "create_note", "concept_name": "external/index-ref", "body": ref_body},
    )
    assert res_ref.status_code == 200, res_ref.text

    # Move directory folder-src -> folder-dest
    move_resp = client.put(
        "/api/v1/wiki/tree/move",
        json={"source_path": "folder-src", "target_path": "folder-dest"},
    )
    assert move_resp.status_code == 200, move_resp.text
    assert move_resp.json()["success"] is True

    # Check both moved files
    from myrm_agent_harness.utils.markdown_frontmatter import parse_frontmatter

    get_alpha = client.get("/api/v1/wiki/concepts/folder-dest/sub/doc-alpha")
    assert get_alpha.status_code == 200, get_alpha.text
    meta_alpha, _ = parse_frontmatter(get_alpha.json()["content"])
    assert meta_alpha.get("canonical_id") == "folder-src.sub.doc-alpha"
    assert "folder-src/sub/doc-alpha" in meta_alpha.get("supersedes", [])

    get_beta = client.get("/api/v1/wiki/concepts/folder-dest/sub/doc-beta")
    assert get_beta.status_code == 200, get_beta.text
    meta_beta, _ = parse_frontmatter(get_beta.json()["content"])
    assert meta_beta.get("canonical_id") == "folder-src.sub.doc-beta"
    assert "folder-src/sub/doc-beta" in meta_beta.get("supersedes", [])

    # Check referrer rewritten
    get_ref = client.get("/api/v1/wiki/concepts/external/index-ref")
    assert get_ref.status_code == 200, get_ref.text
    ref_content = get_ref.json()["editor_sections"]["compiled_truth"]
    assert "[[folder-dest/sub/doc-alpha]]" in ref_content
    assert "[[folder-dest/sub/doc-beta]]" in ref_content


def test_wiki_tree_move_preserves_existing_canonical_id_and_wikilink_anchor(client: TestClient) -> None:
    """Verify idempotency:

    1. Note with existing canonical_id and alias preserves custom metadata on move.
    2. Wikilinks with #anchor are correctly updated without losing anchor.
    """
    from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import CANONICAL_ID_KEY

    # Create note with pre-set canonical_id in frontmatter
    custom_canonical = "custom.hardened.uuid.42"
    res_b = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "vault/custom-note",
            "body": "## Section-42\nContent 42",
            "metadata": {
                CANONICAL_ID_KEY: custom_canonical,
                "aliases": ["legacy-custom-alias"],
            },
        },
    )
    assert res_b.status_code == 200, res_b.text

    # Referrer with wikilink anchor: [[custom-note#Section-42]]
    res_a = client.post(
        "/api/v1/wiki/apply",
        json={
            "op": "create_note",
            "concept_name": "vault/referrer-note",
            "body": "Reference [[vault/custom-note#Section-42|Display Label]]",
        },
    )
    assert res_a.status_code == 200, res_a.text

    # Move custom-note -> relocated/custom-note-v2
    move_resp = client.put(
        "/api/v1/wiki/tree/move",
        json={"source_path": "vault/custom-note", "target_path": "relocated/custom-note-v2"},
    )
    assert move_resp.status_code == 200, move_resp.text
    assert move_resp.json()["success"] is True

    # Check preserved metadata
    from myrm_agent_harness.utils.markdown_frontmatter import parse_frontmatter

    get_new = client.get("/api/v1/wiki/concepts/relocated/custom-note-v2")
    assert get_new.status_code == 200, get_new.text
    meta, _ = parse_frontmatter(get_new.json()["content"])
    # Existing canonical_id must NOT be overwritten
    assert meta.get(CANONICAL_ID_KEY) == custom_canonical
    # Aliases must contain both legacy-custom-alias and vault/custom-note
    aliases = meta.get("aliases", [])
    assert "legacy-custom-alias" in aliases
    assert "vault/custom-note" in aliases

    # Check referrer anchored wikilink rewrite
    get_ref = client.get("/api/v1/wiki/concepts/vault/referrer-note")
    assert get_ref.status_code == 200, get_ref.text
    ref_truth = get_ref.json()["editor_sections"]["compiled_truth"]
    assert "[[relocated/custom-note-v2#Section-42|Display Label]]" in ref_truth
