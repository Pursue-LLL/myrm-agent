import pytest

from myrm_agent_harness.agent.event_log.types import (
    EventFilter,
    EventPayload,
    StructuredEvent,
    ToolUsageStats,
)
from myrm_agent_harness.agent.skills.evolution.pipeline.trace_analyzer import (
    TraceAnalyzer,
)


class MockEventLogBackend:
    def __init__(self, events: list[StructuredEvent]):
        self.events = events

    async def get_events(self, session_id: str, event_filter: EventFilter | None = None) -> list[StructuredEvent]:
        if event_filter is None or event_filter.event_types is None:
            return self.events
        return [event for event in self.events if event.event_type in event_filter.event_types]

    async def append(self, events: list[StructuredEvent]) -> None:
        pass

    async def get_all_session_ids(self) -> list[str]:
        return []

    async def close(self) -> None:
        pass


@pytest.fixture
def mock_backend():
    # Create some mock events
    events = [
        StructuredEvent(
            sequence=1,
            timestamp=1000.0,
            event_type="tool_start",
            session_id="test_session",
            data=EventPayload(tool_name="test_tool", args={}),
        ),
        StructuredEvent(
            sequence=2,
            timestamp=1001.0,
            event_type="tool_failure",
            session_id="test_session",
            data=EventPayload(tool_name="test_tool", error="Permission denied"),
        ),
        StructuredEvent(
            sequence=3,
            timestamp=1002.0,
            event_type="session_end",
            session_id="test_session",
            data=EventPayload(summary={"duration_ms": 2000}),
        ),
    ]
    return MockEventLogBackend(events)


@pytest.mark.asyncio
async def test_extract_trajectory(mock_backend):
    analyzer = TraceAnalyzer(mock_backend)
    result = await analyzer.extract_trajectory("test_session", "test_skill")

    for heading in ("Session Overview", "Failure Analysis", "Tool Stats", "Error Details", "Run Totals"):
        assert f"## {heading}" in result

    # Check if permission error was detected
    assert "permission" in result or "Permission denied" in result


@pytest.mark.asyncio
async def test_analyze_failure_mode_timeout():
    analyzer = TraceAnalyzer(None)  # type: ignore

    tool_stats = []

    error_events = [
        StructuredEvent(
            sequence=1,
            timestamp=1000.0,
            event_type="tool_timeout",
            session_id="test",
            data=EventPayload(),
        )
        for _ in range(4)
    ]

    mode = analyzer._analyze_failure_mode(tool_stats, error_events)
    assert mode == "timeout"


@pytest.mark.asyncio
async def test_analyze_failure_mode_permission():
    analyzer = TraceAnalyzer(None)  # type: ignore

    tool_stats = [
        ToolUsageStats(
            tool_name="test",
            total_calls=1,
            success_count=0,
            failure_count=1,
            timeout_count=0,
            retry_count=0,
            avg_duration_ms=100,
            failure_reasons={"Permission denied": 1},
        )
    ]

    error_events = []

    mode = analyzer._analyze_failure_mode(tool_stats, error_events)
    assert mode == "permission"


@pytest.mark.asyncio
async def test_cluster_similar_errors():
    analyzer = TraceAnalyzer(None)  # type: ignore

    error_events = [
        StructuredEvent(
            sequence=1,
            timestamp=1000.0,
            event_type="tool_failure",
            session_id="test",
            data=EventPayload(error="Connection refused to 10.0.0.1"),
        ),
        StructuredEvent(
            sequence=2,
            timestamp=1001.0,
            event_type="tool_failure",
            session_id="test",
            data=EventPayload(error="Connection refused to 10.0.0.2"),
        ),
        StructuredEvent(
            sequence=3,
            timestamp=1002.0,
            event_type="tool_failure",
            session_id="test",
            data=EventPayload(error="File not found: /tmp/a"),
        ),
    ]

    clusters = analyzer._cluster_similar_errors(error_events)
    # Should cluster the two connection refused errors together
    assert len(clusters) == 2
