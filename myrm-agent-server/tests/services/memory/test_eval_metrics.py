"""Tests for Memory Command Center eval metrics (Server layer).

Validates build_eval_metrics() correctly produces cross_session_transfer
eval metric from SearchMetrics snapshot data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.memory.command_center import (
    MemoryCommandInfluenceItem,
    MemoryCommandMigrationProvenance,
    MemoryCommandTimelineEvent,
)
from app.services.memory.command_center_insights import MemoryCommandCenterInsights


@pytest.fixture
def insights() -> MemoryCommandCenterInsights:
    return MemoryCommandCenterInsights(
        db=MagicMock(),
        memory_manager=AsyncMock(),
        ledger=MagicMock(),
    )


@pytest.fixture
def migration() -> MemoryCommandMigrationProvenance:
    return MemoryCommandMigrationProvenance(
        supported_sources=["chatgpt"],
        tracked_imports=5,
        unmapped_items=0,
        coverage_status="complete",
    )


def _make_snapshot(
    cross_session_hits: int = 0,
    total_sourced_hits: int = 0,
    cross_session_hit_rate: float = 0.0,
) -> MagicMock:
    snap = MagicMock()
    snap.cross_session_hits = cross_session_hits
    snap.total_sourced_hits = total_sourced_hits
    snap.cross_session_hit_rate = cross_session_hit_rate
    return snap


class TestBuildEvalMetrics:
    """build_eval_metrics() cross_session_transfer eval metric."""

    @patch("app.services.memory.command_center_insights.get_search_metrics")
    def test_cross_session_transfer_present(
        self,
        mock_get: MagicMock,
        insights: MemoryCommandCenterInsights,
        migration: MemoryCommandMigrationProvenance,
    ) -> None:
        mock_get.return_value.snapshot.return_value = _make_snapshot(
            cross_session_hits=10,
            total_sourced_hits=20,
            cross_session_hit_rate=0.5,
        )

        result = insights.build_eval_metrics(
            timeline=[],
            influence=[],
            conflicts=[],
            migration=migration,
        )

        ids = [m.id for m in result]
        assert "cross_session_transfer" in ids

        cs_metric = next(m for m in result if m.id == "cross_session_transfer")
        assert cs_metric.status == "ready"
        assert "50%" in cs_metric.evidence
        assert "10 cross-session" in cs_metric.evidence
        assert "20 sourced" in cs_metric.evidence

    @patch("app.services.memory.command_center_insights.get_search_metrics")
    def test_cross_session_transfer_missing_when_zero_hits(
        self,
        mock_get: MagicMock,
        insights: MemoryCommandCenterInsights,
        migration: MemoryCommandMigrationProvenance,
    ) -> None:
        mock_get.return_value.snapshot.return_value = _make_snapshot()

        result = insights.build_eval_metrics(
            timeline=[],
            influence=[],
            conflicts=[],
            migration=migration,
        )

        cs_metric = next(m for m in result if m.id == "cross_session_transfer")
        assert cs_metric.status == "missing"
        assert "0%" in cs_metric.evidence

    @patch("app.services.memory.command_center_insights.get_search_metrics")
    def test_cross_session_transfer_partial_when_few_hits(
        self,
        mock_get: MagicMock,
        insights: MemoryCommandCenterInsights,
        migration: MemoryCommandMigrationProvenance,
    ) -> None:
        mock_get.return_value.snapshot.return_value = _make_snapshot(
            cross_session_hits=3,
            total_sourced_hits=10,
            cross_session_hit_rate=0.3,
        )

        result = insights.build_eval_metrics(
            timeline=[],
            influence=[],
            conflicts=[],
            migration=migration,
        )

        cs_metric = next(m for m in result if m.id == "cross_session_transfer")
        assert cs_metric.status == "partial"

    @patch("app.services.memory.command_center_insights.get_search_metrics")
    def test_eval_metrics_count(
        self,
        mock_get: MagicMock,
        insights: MemoryCommandCenterInsights,
        migration: MemoryCommandMigrationProvenance,
    ) -> None:
        """Should produce exactly 5 eval metrics."""
        mock_get.return_value.snapshot.return_value = _make_snapshot()

        result = insights.build_eval_metrics(
            timeline=[],
            influence=[],
            conflicts=[],
            migration=migration,
        )

        assert len(result) == 5

    @patch("app.services.memory.command_center_insights.get_search_metrics")
    def test_eval_metrics_with_timeline_influence(
        self,
        mock_get: MagicMock,
        insights: MemoryCommandCenterInsights,
        migration: MemoryCommandMigrationProvenance,
    ) -> None:
        """Event coverage and influence coverage respond to input data."""
        mock_get.return_value.snapshot.return_value = _make_snapshot()

        events = [MagicMock(spec=MemoryCommandTimelineEvent)] * 12
        influence_item = MagicMock(spec=MemoryCommandInfluenceItem)
        influence_item.influence_refs = ["ref1", "ref2", "ref3"]

        result = insights.build_eval_metrics(
            timeline=events,
            influence=[influence_item, influence_item],
            conflicts=[],
            migration=migration,
        )

        event_metric = next(m for m in result if m.id == "event_coverage")
        assert event_metric.status == "ready"
        influence_metric = next(m for m in result if m.id == "influence_coverage")
        assert influence_metric.status == "ready"
