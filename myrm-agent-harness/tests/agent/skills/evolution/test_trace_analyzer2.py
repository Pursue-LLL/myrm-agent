from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.event_log.protocols import EventLogBackend
from myrm_agent_harness.agent.skills.evolution.pipeline.trace_analyzer import TraceAnalyzer


@pytest.fixture
def mock_backend():
    return AsyncMock(spec=EventLogBackend)


@pytest.mark.asyncio
async def test_extract_trajectory_with_code(mock_backend):
    # Mock extract_trajectory
    analyzer = TraceAnalyzer(backend=mock_backend)
    analyzer.extract_trajectory = AsyncMock(return_value="Trace history")

    skill = MagicMock()
    skill.skill_id = "test_skill"
    skill.content = "def test():\n    pass"

    result = await analyzer.extract_trajectory_with_code("session_1", skill)
    assert "Trace history" in result
    assert "def test():\n    pass" in result


@pytest.mark.asyncio
async def test_extract_trajectory_no_backend():
    analyzer = TraceAnalyzer(backend=None)
    result = await analyzer.extract_trajectory("session_1", "test_skill")
    assert "unavailable" in result
