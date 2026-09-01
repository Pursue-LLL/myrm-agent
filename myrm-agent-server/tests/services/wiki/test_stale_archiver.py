"""Unit tests for StaleFileArchiver service."""

from pathlib import Path
import pytest

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from app.services.wiki.maintain.stale_archiver import StaleFileArchiver
from myrm_agent_harness.toolkits.wiki.core.fact_trust_contract import FactStatus


def test_stale_file_archiver_scan_and_archive(tmp_path: Path) -> None:
    vault = tmp_path / "test_vault"
    vault.mkdir()
    structure = WikiStructure(vault)
    structure.ensure_structure()

    # Create a published truth concept
    truth_file = structure.get_concept_file_path("truth_doc")
    truth_file.write_text("---\nfact_status: published_truth\n---\n# Truth", encoding="utf-8")

    # Create an explicitly deprecated concept
    deprecated_file = structure.get_concept_file_path("deprecated_doc")
    deprecated_file.write_text("---\nfact_status: deprecated\n---\n# Deprecated", encoding="utf-8")

    archiver = StaleFileArchiver(structure)
    scan_result = archiver.scan_stale_files()

    assert scan_result.scanned_count >= 2
    assert len(scan_result.stale_candidates) == 1
    assert scan_result.stale_candidates[0].fact_status == FactStatus.DEPRECATED

    # Perform archival
    archive_result = archiver.archive_candidates([scan_result.stale_candidates[0].file_path])
    assert archive_result.archived_count == 1
    assert not deprecated_file.exists()
    assert (vault / "wiki" / "archive" / "deprecated_doc.md").exists()
