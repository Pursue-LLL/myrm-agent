"""ServerSkillExecutionProvider reads execution samples from EventLog."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import EventPayload, StructuredEvent
from myrm_agent_harness.agent.skills.optimization.event_adapter import EventLogAdapter
from myrm_agent_harness.core.events.types import AgentEventType

from app.services.skill_optimization.execution_provider import ServerSkillExecutionProvider


@pytest.mark.asyncio
async def test_get_skill_executions_from_event_log(tmp_path) -> None:
    log_dir = tmp_path / "event_logs"
    session_id = "sess-a"
    backend = FileEventLogBackend(log_dir=log_dir, session_id=session_id)
    now = time.time()
    await backend.append(
        [
            StructuredEvent(
                sequence=1,
                timestamp=now,
                event_type=AgentEventType.TOOL_START.value,
                session_id=session_id,
                data=EventPayload(tool_name="my-skill", tool_call_id="id-1", start_time=now, status="started"),
            ),
            StructuredEvent(
                sequence=2,
                timestamp=now + 1.0,
                event_type=AgentEventType.TOOL_END.value,
                session_id=session_id,
                data=EventPayload(
                    tool_name="my-skill",
                    tool_call_id="id-1",
                    start_time=now,
                    end_time=now + 1.0,
                    duration_ms=1000,
                    status="completed",
                ),
            ),
        ]
    )

    provider = ServerSkillExecutionProvider(event_log_adapter=EventLogAdapter(backend))

    with patch.object(
        provider,
        "_tool_name_aliases",
        new=AsyncMock(return_value=frozenset({"my-skill"})),
    ):
        samples = await provider.get_skill_executions("skill-uuid-1", days=7)
        count = await provider.count_executions("skill-uuid-1", days=7)

    assert len(samples) == 1
    assert samples[0].success is True
    assert count == 1


@pytest.mark.asyncio
async def test_get_skill_metadata_returns_none_when_missing(tmp_path) -> None:
    provider = ServerSkillExecutionProvider(event_log_adapter=EventLogAdapter(FileEventLogBackend(tmp_path, "x")))

    with patch(
        "app.core.skills.store.service.skills_service.get_skill",
        new=AsyncMock(return_value=None),
    ):
        assert await provider.get_skill_metadata("missing") is None
