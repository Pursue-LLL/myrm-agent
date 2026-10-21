"""Unit tests for curator service get_stats_collector injection."""

from __future__ import annotations

import pytest
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.usage_recorder import (
    get_injected_stats_collector,
    set_stats_collector,
)


@pytest.fixture(autouse=True)
def _reset_curator_singletons() -> None:
    import app.core.skills.curator.service as curator_service

    curator_service._stats_collector = None
    set_stats_collector(None)
    yield
    curator_service._stats_collector = None
    set_stats_collector(None)


def test_get_stats_collector_injects_into_harness() -> None:
    from app.core.skills.curator import service as curator_service

    collector = curator_service.get_stats_collector()

    assert isinstance(collector, SkillStatsCollector)
    assert get_injected_stats_collector() is collector

    again = curator_service.get_stats_collector()
    assert again is collector
