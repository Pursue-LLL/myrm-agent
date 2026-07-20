"""Unit tests for curator_service get_stats_collector injection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.usage_recorder import (
    get_injected_stats_collector,
    set_stats_collector,
)


@pytest.fixture(autouse=True)
def _reset_curator_singletons() -> None:
    import app.core.skills.curator_service as curator_service

    curator_service._stats_collector = None
    set_stats_collector(None)
    yield
    curator_service._stats_collector = None
    set_stats_collector(None)


def test_get_stats_collector_injects_into_harness(tmp_path: Path) -> None:
    from app.core.skills import curator_service

    skills_root = tmp_path / "skills"
    skills_root.mkdir()

    with patch.object(curator_service, "_get_skills_root", return_value=skills_root):
        collector = curator_service.get_stats_collector()

    assert isinstance(collector, SkillStatsCollector)
    assert get_injected_stats_collector() is collector

    again = curator_service.get_stats_collector()
    assert again is collector
