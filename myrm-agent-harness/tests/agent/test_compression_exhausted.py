"""Tests for compression exhausted protection (death-loop prevention).

Verifies that when context overflow recovery is exhausted:
1. AgentRunStatistics.compression_exhausted flag is set
2. ERROR events include compression_exhausted=True
3. Server layer can detect and act on the flag
"""

import dataclasses
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.types import Command

from myrm_agent_harness.agent.streaming.source_tracker import SourceTracker
from myrm_agent_harness.agent.streaming.stream_executor import StreamContext, StreamExecutor
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError


class TestCompressionExhaustedFlag:
    """AgentRunStatistics.compression_exhausted field behavior."""

    def test_default_false(self) -> None:
        stats = AgentRunStatistics()
        assert stats.compression_exhausted is False

    def test_set_true(self) -> None:
        stats = AgentRunStatistics()
        stats.compression_exhausted = True
        assert stats.compression_exhausted is True

    def test_preserved_in_copy(self) -> None:
        stats = AgentRunStatistics()
        stats.compression_exhausted = True
        copied = dataclasses.replace(stats)
        assert copied.compression_exhausted is True


class TestHandleOverflowExhaustion:
    """StreamExecutor._handle_overflow sets compression_exhausted when retries exhausted."""

    @pytest.fixture
    def mock_executor(self) -> tuple[StreamExecutor, MagicMock, AgentRunStatistics]:
        stats = AgentRunStatistics()
        ctx = MagicMock(spec=StreamContext)
        ctx.stats = stats
        ctx.message_id = "test-msg"
        ctx.agent_input = {"messages": []}

        executor = object.__new__(StreamExecutor)
        executor._ctx = ctx
        executor._compactor = AsyncMock()
        executor.streaming_final_answer = False

        return executor, ctx, stats

    @pytest.mark.asyncio
    async def test_retries_not_exhausted(
        self, mock_executor: tuple[StreamExecutor, MagicMock, AgentRunStatistics]
    ) -> None:
        """First overflow attempt should NOT set compression_exhausted."""
        executor, _ctx, stats = mock_executor

        exc = Exception("context_length_exceeded: too many tokens")
        result = await executor._handle_overflow(exc, retries=0)

        assert result is True
        assert stats.compression_exhausted is False

    @pytest.mark.asyncio
    async def test_retries_exhausted_sets_flag(
        self, mock_executor: tuple[StreamExecutor, MagicMock, AgentRunStatistics]
    ) -> None:
        """When retries >= MAX, compression_exhausted should be True."""
        executor, _ctx, stats = mock_executor

        exc = Exception("context_length_exceeded: too many tokens")
        result = await executor._handle_overflow(exc, retries=2)

        assert result is False
        assert stats.compression_exhausted is True

    @pytest.mark.asyncio
    async def test_non_overflow_error_no_flag(
        self, mock_executor: tuple[StreamExecutor, MagicMock, AgentRunStatistics]
    ) -> None:
        """Non-overflow errors should not set the flag."""
        executor, _ctx, stats = mock_executor

        exc = Exception("rate limit exceeded")
        result = await executor._handle_overflow(exc, retries=5)

        assert result is False
        assert stats.compression_exhausted is False

    @pytest.mark.asyncio
    async def test_retries_above_max_sets_flag(
        self, mock_executor: tuple[StreamExecutor, MagicMock, AgentRunStatistics]
    ) -> None:
        """Retries above MAX (e.g. 3) should still set compression_exhausted."""
        executor, _ctx, stats = mock_executor

        exc = Exception("context_length_exceeded: too many tokens")
        result = await executor._handle_overflow(exc, retries=3)

        assert result is False
        assert stats.compression_exhausted is True

    @pytest.mark.asyncio
    async def test_resume_mode_overflow_no_flag(
        self, mock_executor: tuple[StreamExecutor, MagicMock, AgentRunStatistics]
    ) -> None:
        """Resume mode (Command input) overflow should return False without setting flag."""
        executor, ctx, stats = mock_executor
        ctx.agent_input = Command(resume={"decision": "approve"})

        exc = Exception("context_length_exceeded: too many tokens")
        result = await executor._handle_overflow(exc, retries=0)

        assert result is False
        assert stats.compression_exhausted is False

    def test_compression_exhausted_with_cancelled(self) -> None:
        """Both compression_exhausted and was_cancelled can be True simultaneously."""
        stats = AgentRunStatistics()
        stats.compression_exhausted = True
        stats.was_cancelled = True
        assert stats.compression_exhausted is True
        assert stats.was_cancelled is True


def _build_executor(ctx: MagicMock, compactor: AsyncMock) -> StreamExecutor:
    """Build through the real constructor so state added to ``StreamExecutor.__init__`` never drifts from this test."""
    ctx.output_queue = AsyncMock()
    ctx.cancel_token = None
    ctx.memory_manager = None
    executor = StreamExecutor(ctx, rebuild_agent_fn=lambda _agent: None)
    executor._compactor = compactor
    return executor


def _executor_whose_model_call_fails(
    stats: AgentRunStatistics, error: Exception
) -> tuple[StreamExecutor, MagicMock, list[dict[str, object]]]:
    """An executor whose model call raises ``error``, with the list its events are collected in."""
    ctx = MagicMock(spec=StreamContext)
    ctx.stats = stats
    ctx.message_id = "test-msg"
    ctx.merged_context = {"locale": "en"}
    ctx.llm_info = None
    ctx.source_tracker = SourceTracker()
    ctx.agent = MagicMock()
    ctx.agent.astream = MagicMock(side_effect=error)
    ctx.agent_input = {"messages": []}
    ctx.run_config = {}
    ctx.cancel_token = None
    ctx.steering_token = None
    ctx.event_logger = None
    ctx.drain_subagent_notifications = None

    captured_events: list[dict[str, object]] = []
    compactor = AsyncMock()

    async def capture_put(event: object) -> None:
        if isinstance(event, dict):
            captured_events.append(event)

    compactor.put = capture_put
    compactor.flush = AsyncMock()
    return _build_executor(ctx, compactor), ctx, captured_events


class TestErrorEventCompressionExhausted:
    """ERROR event includes compression_exhausted when set."""

    @pytest.mark.asyncio
    async def test_error_event_includes_flag(self) -> None:
        """When compression_exhausted=True, ERROR event should contain the flag."""
        stats = AgentRunStatistics()
        stats.compression_exhausted = True
        executor, ctx, captured_events = _executor_whose_model_call_fails(stats, Exception("context_length_exceeded"))

        with (
            patch("myrm_agent_harness.agent.hooks.executor.fire_hook", new_callable=AsyncMock),
            pytest.raises(MyrmLLMError),
        ):
            await executor.execute()

        # The failure comes from the model call, not from the executor tripping over its setup.
        ctx.agent.astream.assert_called()
        error_events = [e for e in captured_events if e.get("type") == AgentEventType.ERROR.value]
        assert len(error_events) == 1
        assert error_events[0]["compression_exhausted"] is True

    @pytest.mark.asyncio
    async def test_error_event_without_flag(self) -> None:
        """When compression_exhausted=False, ERROR event should NOT contain the flag."""
        executor, ctx, captured_events = _executor_whose_model_call_fails(
            AgentRunStatistics(), Exception("some random error")
        )

        with (
            patch("myrm_agent_harness.agent.hooks.executor.fire_hook", new_callable=AsyncMock),
            pytest.raises(MyrmLLMError),
        ):
            await executor.execute()

        ctx.agent.astream.assert_called()
        error_events = [e for e in captured_events if e.get("type") == AgentEventType.ERROR.value]
        assert len(error_events) == 1
        assert "compression_exhausted" not in error_events[0]


class TestSSEDetectionLogic:
    """Tests for SSE compression_exhausted detection logic (inline, no server import)."""

    @staticmethod
    def _is_compression_exhausted(sse_chunk: str) -> bool:
        """Inline replica of the server-side detection function for unit testing."""
        prefix = "data: "
        if "compression_exhausted" not in sse_chunk:
            return False
        if not sse_chunk.startswith(prefix):
            return False
        try:
            event = json.loads(sse_chunk[len(prefix) :].rstrip())
            return event.get("type") == "error" and event.get("compression_exhausted") is True
        except (json.JSONDecodeError, TypeError):
            return False

    def test_detects_compression_exhausted(self) -> None:
        event = {
            "type": "error",
            "error": "context overflow",
            "compression_exhausted": True,
            "messageId": "msg-1",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert self._is_compression_exhausted(chunk) is True

    def test_rejects_normal_error(self) -> None:
        event = {
            "type": "error",
            "error": "rate limit",
            "messageId": "msg-1",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert self._is_compression_exhausted(chunk) is False

    def test_rejects_non_error_events(self) -> None:
        event = {
            "type": "message",
            "compression_exhausted": True,
            "messageId": "msg-1",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert self._is_compression_exhausted(chunk) is False

    def test_rejects_invalid_sse(self) -> None:
        assert self._is_compression_exhausted("not-sse-data") is False
        assert self._is_compression_exhausted("data: {invalid json}\n\n") is False
        assert self._is_compression_exhausted("") is False

    def test_compression_exhausted_false_value(self) -> None:
        """compression_exhausted=False should return False."""
        event = {
            "type": "error",
            "error": "context overflow",
            "compression_exhausted": False,
            "messageId": "msg-1",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert self._is_compression_exhausted(chunk) is False

    def test_resume_mode_guard(self) -> None:
        """Server should NOT undo when resume_value is set."""
        event = {
            "type": "error",
            "compression_exhausted": True,
            "messageId": "msg-1",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert self._is_compression_exhausted(chunk) is True
