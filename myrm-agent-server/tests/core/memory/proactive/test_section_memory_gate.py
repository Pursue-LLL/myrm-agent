"""Tests for proactive follow-up heartbeat section."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from myrm_agent_harness.toolkits.cron.situation import SituationContext


@pytest.mark.asyncio
async def test_pending_section_skips_when_memory_disabled() -> None:
    from app.core.memory.proactive.section import PendingCommitmentsSection

    section = PendingCommitmentsSection()
    ctx = SituationContext(
        last_tick_at=datetime.now(UTC),
        agent_id="agent-1",
        user_id="default",
        memory_enabled=False,
    )
    result = await section.build(ctx)
    assert result is None
