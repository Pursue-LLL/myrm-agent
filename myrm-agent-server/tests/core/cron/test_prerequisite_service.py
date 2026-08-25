"""Unit tests for CronPrerequisiteService and Prerequisite Check API."""

import pytest

from app.services.cron.prerequisite_service import (
    DEFAULT_PREREQUISITE_THRESHOLD,
    CronPrerequisiteService,
)


@pytest.mark.asyncio
async def test_prerequisite_service_basic():
    stats = await CronPrerequisiteService.get_prerequisite_stats(
        prompt="Daily summary of AI news",
        agent_id="test_agent",
        threshold=2,
    )
    assert len(stats.fingerprint) == 64
    assert stats.threshold == 2
    assert isinstance(stats.manual_success_count, int)
    assert isinstance(stats.is_satisfied, bool)
    assert stats.override_allowed is True


@pytest.mark.asyncio
async def test_prerequisite_service_edge_cases():
    # Test with empty parameters
    stats_empty = await CronPrerequisiteService.get_prerequisite_stats(
        prompt="",
        agent_id=None,
        threshold=1,
    )
    assert len(stats_empty.fingerprint) == 64
    assert stats_empty.threshold == 1

    # Test with tools and custom threshold
    stats_tools = await CronPrerequisiteService.get_prerequisite_stats(
        prompt="Execute command in shell",
        agent_id="dev-agent",
        command="ls -la",
        tools_allowed=["shell", "read_file"],
        threshold=DEFAULT_PREREQUISITE_THRESHOLD,
    )
    assert len(stats_tools.fingerprint) == 64
    assert stats_tools.threshold == DEFAULT_PREREQUISITE_THRESHOLD

