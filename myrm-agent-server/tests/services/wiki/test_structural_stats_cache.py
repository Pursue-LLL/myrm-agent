"""Tests for structural lint stats TTL cache."""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.structural_stats_cache import (
    get_structural_lint_snapshot_cached,
    invalidate_structural_lint_cache,
)


def test_structural_stats_cache_hit(tmp_path: Path) -> None:
    structure = WikiStructure(tmp_path)
    structure.ensure_structure()

    first = get_structural_lint_snapshot_cached(structure)
    second = get_structural_lint_snapshot_cached(structure)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.snapshot.scanned_concepts == first.snapshot.scanned_concepts


def test_structural_stats_cache_invalidate(tmp_path: Path) -> None:
    structure = WikiStructure(tmp_path)
    structure.ensure_structure()

    get_structural_lint_snapshot_cached(structure)
    invalidate_structural_lint_cache(structure)
    refreshed = get_structural_lint_snapshot_cached(structure)

    assert refreshed.cache_hit is False
