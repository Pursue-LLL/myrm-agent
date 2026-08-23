"""Unit tests for CronPrerequisiteService and Prerequisite Check API."""

import pytest
from app.services.cron.prerequisite_service import CronPrerequisiteService


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
