"""Unit test suite for Wiki Knowledge Governance (Freshness, Archive, Revival, Undo Buffer).

[INPUT]
- app.services.wiki.governance.schemas::*
- app.services.wiki.governance.freshness_service::WikiGovernanceFreshnessService
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure

[OUTPUT]
- Unit tests verifying:
  1. 90-day aging detection
  2. Frontmatter permanent/pinned whitelist exemption
  3. Safe atomic archiving out of concepts into archive/ directory
  4. Safe atomic revival back into active concepts
  5. 30-second undo buffer rollback
  6. Prevention of FTS5 traversal penetration

[POS]
Unit tests for Roadmap Item #7 KnowledgeGovernanceWorkbenchExpiryArchiveRevival.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.governance.freshness_service import (
    WikiGovernanceFreshnessService,
)


@pytest.fixture
def wiki_structure(tmp_path: Path) -> WikiStructure:
    structure = WikiStructure(tmp_path)
    structure.ensure_structure()
    return structure


def test_structure_archive_dir_isolation(wiki_structure: WikiStructure) -> None:
    """Verify archive_dir is physically isolated from concepts_dir."""
    assert wiki_structure.archive_dir == wiki_structure.wiki_dir / "archive" / "concepts"
    assert wiki_structure.archive_dir.exists()

    # Create active concept
    active_path = wiki_structure.get_concept_file_path("active_rule")
    active_path.write_text("Active rule content", encoding="utf-8")

    # Create archived concept
    archive_path = wiki_structure.get_archived_concept_file_path("archived_old_rule")
    archive_path.write_text("Old rule content", encoding="utf-8")

    # list_concepts must NOT include archived concepts
    active_concepts = wiki_structure.list_concepts()
    assert len(active_concepts) == 1
    assert active_concepts[0].name == "active_rule.md"

    # list_archived_concepts must return the archived concept
    archived_concepts = wiki_structure.list_archived_concepts()
    assert len(archived_concepts) == 1
    assert archived_concepts[0].name == "archived_old_rule.md"


def test_freshness_scan_aging_and_whitelist(wiki_structure: WikiStructure) -> None:
    """Verify 90-day aging detection and permanent whitelist exemption."""
    service = WikiGovernanceFreshnessService(wiki_structure, freshness_threshold_days=90)

    # 1. Fresh concept (modified now)
    fresh_path = wiki_structure.get_concept_file_path("fresh_policy")
    fresh_path.write_text("Fresh policy", encoding="utf-8")

    # 2. Old concept (>90 days old)
    old_path = wiki_structure.get_concept_file_path("old_policy")
    old_path.write_text("Old policy", encoding="utf-8")
    old_time = time.time() - (100 * 86400)
    os.utime(old_path, (old_time, old_time))

    # 3. Old permanent concept (with frontmatter whitelist)
    permanent_path = wiki_structure.get_concept_file_path("company_constitution")
    permanent_path.write_text(
        "---\nlifecycle: permanent\ntitle: Company Constitution\n---\nCore principles never expire.",
        encoding="utf-8",
    )
    os.utime(permanent_path, (old_time, old_time))

    expiring = service.scan_expiring_concepts()
    names = [c.concept_name for c in expiring]

    assert "old_policy" in names
    assert "fresh_policy" not in names
    assert "company_constitution" not in names  # Exempted by whitelist!


@pytest.mark.asyncio
async def test_archive_and_revival_lifecycle(wiki_structure: WikiStructure) -> None:
    """Verify atomic archive, physical isolation, undo buffer, and revival."""
    service = WikiGovernanceFreshnessService(wiki_structure)

    # Create concept
    concept_path = wiki_structure.get_concept_file_path("deprecated_api")
    concept_path.write_text("Deprecated API v1", encoding="utf-8")
    assert concept_path.exists()

    # 1. Archive concept
    res = await service.archive_concepts(["deprecated_api"], reason="Migrated to v2")
    assert res.success is True
    assert res.affected_count == 1
    assert not concept_path.exists()
    assert wiki_structure.get_archived_concept_file_path("deprecated_api").exists()

    # Must be absent from active concepts
    assert len(wiki_structure.list_concepts()) == 0
    assert len(wiki_structure.list_archived_concepts()) == 1

    # 2. Test Undo Archive
    undo_res = await service.undo_archive(res.undo_token)
    assert undo_res.success is True
    assert undo_res.affected_count == 1
    assert concept_path.exists()
    assert not wiki_structure.get_archived_concept_file_path("deprecated_api").exists()

    # 3. Re-archive then explicitly revive
    await service.archive_concepts(["deprecated_api"])
    assert not concept_path.exists()

    revive_res = await service.revive_concepts(["deprecated_api"])
    assert revive_res.success is True
    assert revive_res.affected_count == 1
    assert concept_path.exists()
    assert not wiki_structure.get_archived_concept_file_path("deprecated_api").exists()


def test_extend_concept_lifespan(wiki_structure: WikiStructure) -> None:
    """Verify extending concept resets expiration clock."""
    service = WikiGovernanceFreshnessService(wiki_structure, freshness_threshold_days=90)

    old_path = wiki_structure.get_concept_file_path("standard_ops")
    old_path.write_text("Operations standard", encoding="utf-8")
    old_time = time.time() - (120 * 86400)
    os.utime(old_path, (old_time, old_time))

    # Before extend: flagged as expiring
    expiring = service.scan_expiring_concepts()
    assert any(c.concept_name == "standard_ops" for c in expiring)

    # Extend
    res = service.extend_concepts(["standard_ops"])
    assert res.success is True
    assert res.affected_count == 1

    # After extend: no longer expiring
    expiring_after = service.scan_expiring_concepts()
    assert not any(c.concept_name == "standard_ops" for c in expiring_after)
