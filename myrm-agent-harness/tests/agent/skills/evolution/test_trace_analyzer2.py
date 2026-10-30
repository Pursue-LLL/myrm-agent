import pytest

from myrm_agent_harness.agent.skills.evolution.pipeline.trace_analyzer import TraceAnalyzer


@pytest.mark.asyncio
async def test_extract_trajectory_no_backend():
    analyzer = TraceAnalyzer(backend=None)
    result = await analyzer.extract_trajectory("session_1", "test_skill")
    assert "unavailable" in result
