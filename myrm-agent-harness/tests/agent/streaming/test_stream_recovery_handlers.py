"""Tests for stream_recovery.py and stream_recovery_turn_end.py — transient retry, iteration limit, empty response.

Covers:
- _handle_transient_retry (backoff, exhaustion, cancel)
- _handle_iteration_limit (GraphRecursionError detection)
- _handle_empty_response (injection, exhaustion)
- _handle_overflow stage 2 (retries==1)
"""

import asyncio
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.streaming.stream_executor import (
    StreamContext,
    StreamExecutor,
)
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics

from .scripted_agent import recover_empty_reply


class FakeCompactor:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def put(self, event: object) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        pass


@pytest.fixture
def ctx():
    stats = AgentRunStatistics()
    return StreamContext(
        agent=MagicMock(),
        agent_input={"messages": [HumanMessage(content="test")]},
        merged_context={"locale": "en"},
        run_config={},
        stats=stats,
        message_id="recovery_test",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
    )


def _make_executor(
    ctx: StreamContext,
    fallback_llm: object | None = None,
    safety_fallback_llm: object | None = None,
) -> StreamExecutor:
    executor = StreamExecutor(
        ctx=ctx,
        fallback_llm=fallback_llm,
        safety_fallback_llm=safety_fallback_llm,
        rebuild_agent_fn=MagicMock(),
    )
    executor._compactor = FakeCompactor()
    return executor


# ─── _handle_overflow stage 2 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overflow_stage2_truncation(ctx):
    """Stage 2 (retries==1) goes directly to truncation."""
    executor = _make_executor(ctx)
    exc = RuntimeError("context length exceeded")

    with (
        patch(
            "myrm_agent_harness.agent.streaming.recovery.stream_recovery.is_context_overflow",
            return_value=True,
        ),
        patch(
            "myrm_agent_harness.agent.streaming.recovery.stream_recovery._truncate_oldest_rounds",
            return_value=300,
        ) as truncate_mock,
    ):
        result = await executor._handle_overflow(exc, 1)

    assert result is True
    truncate_mock.assert_called_once()


# ─── _handle_transient_retry ─────────────────────────────────────────────────


class TestHandleTransientRetry:
    @pytest.mark.asyncio
    async def test_non_transient_error(self, ctx):
        """Non-transient error → returns False."""
        executor = _make_executor(ctx)

        from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

        with patch(
            "myrm_agent_harness.agent.streaming.recovery.stream_recovery.classify_error",
            return_value=ErrorKind.AUTH,
        ):
            result = await executor._handle_transient_retry(RuntimeError("auth"), 0)
        assert result is False

    @pytest.mark.asyncio
    async def test_rejected_certificate_is_not_retried(self, ctx):
        """Waiting cannot change a certificate verdict, however the client library words the failure."""
        executor = _make_executor(ctx)
        wrapper = httpx.ConnectError("")
        wrapper.__cause__ = ssl.SSLCertVerificationError(
            1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
        )

        with patch(
            "myrm_agent_harness.agent.streaming.recovery.stream_recovery_window.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            result = await executor._handle_transient_retry(wrapper, 0)

        assert result is False
        sleep.assert_not_called()
        assert not executor._compactor.events

    @pytest.mark.asyncio
    async def test_transient_rate_limit_retry(self, ctx):
        """Rate limit triggers retry with backoff."""
        executor = _make_executor(ctx)

        from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

        with (
            patch(
                "myrm_agent_harness.agent.streaming.recovery.stream_recovery.classify_error",
                return_value=ErrorKind.RATE_LIMIT,
            ),
            patch(
                "myrm_agent_harness.agent.streaming.recovery.stream_recovery_window.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await executor._handle_transient_retry(RuntimeError("rate limited"), 0)
        assert result is True
        events = executor._compactor.events
        retry_events = [e for e in events if isinstance(e, dict) and e.get("step_key") == "transient_retry"]
        assert len(retry_events) == 1
        assert retry_events[0]["restart"] is True

    @pytest.mark.asyncio
    async def test_transient_exhausted(self, ctx):
        """Retries exhausted → returns False."""
        executor = _make_executor(ctx)

        from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

        with patch(
            "myrm_agent_harness.agent.streaming.recovery.stream_recovery.classify_error",
            return_value=ErrorKind.RATE_LIMIT,
        ):
            result = await executor._handle_transient_retry(RuntimeError("rate limited"), 15)
        assert result is False

    @pytest.mark.asyncio
    async def test_transient_cancelled(self, ctx):
        """Cancel token cancels the retry."""
        cancel = MagicMock()
        cancel.is_cancelled = True
        ctx.cancel_token = cancel

        executor = _make_executor(ctx)

        from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

        with (
            patch(
                "myrm_agent_harness.agent.streaming.recovery.stream_recovery.classify_error",
                return_value=ErrorKind.TIMEOUT,
            ),
            patch(
                "myrm_agent_harness.agent.streaming.recovery.stream_recovery_window.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await executor._handle_transient_retry(RuntimeError("timeout"), 0)
        assert result is False

    @pytest.mark.asyncio
    async def test_transient_overloaded(self, ctx):
        """OVERLOADED error is transient."""
        executor = _make_executor(ctx)

        from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

        with (
            patch(
                "myrm_agent_harness.agent.streaming.recovery.stream_recovery.classify_error",
                return_value=ErrorKind.OVERLOADED,
            ),
            patch(
                "myrm_agent_harness.agent.streaming.recovery.stream_recovery_window.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await executor._handle_transient_retry(RuntimeError("overloaded"), 0)
        assert result is True

    @pytest.mark.asyncio
    async def test_transient_quota_exhausted_bypasses_retry(self, ctx):
        """Quota exhausted error (insufficient_quota) must bypass transient retry immediately."""
        executor = _make_executor(ctx)

        from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

        # Even if classify_error might classify it as RATE_LIMIT or OVERLOADED,
        # is_quota_exhausted short-circuits it and returns False.
        with (
            patch(
                "myrm_agent_harness.agent.streaming.recovery.stream_recovery.classify_error",
                return_value=ErrorKind.RATE_LIMIT,
            ),
            patch(
                "myrm_agent_harness.agent.streaming.recovery.stream_recovery_window.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
        ):
            result = await executor._handle_transient_retry(
                RuntimeError("insufficient_quota: You exceeded your current quota"), 0
            )

        assert result is False
        mock_sleep.assert_not_called()
        # Verify no transient_retry events were emitted
        events = executor._compactor.events
        retry_events = [e for e in events if isinstance(e, dict) and e.get("step_key") == "transient_retry"]
        assert len(retry_events) == 0


# ─── _handle_iteration_limit ─────────────────────────────────────────────────


class TestHandleIterationLimit:
    @pytest.mark.asyncio
    async def test_graph_recursion_error(self, ctx):
        """GraphRecursionError triggers iteration limit handling + grace call."""
        from langgraph.errors import GraphRecursionError

        executor = _make_executor(ctx)
        ctx.run_config["recursion_limit"] = 25
        ctx.stats.node_execution_count = 24

        exc = GraphRecursionError("limit reached")
        msgs = [HumanMessage(content="test")]
        result = await executor._handle_iteration_limit(exc, msgs)

        assert result is True
        events = executor._compactor.events
        limit_events = [
            e for e in events if isinstance(e, dict) and e.get("type") == AgentEventType.ITERATION_LIMIT_REACHED.value
        ]
        assert len(limit_events) == 1
        assert limit_events[0]["data"]["limit"] == 25
        assert limit_events[0]["data"]["nodes_completed"] == 24

    @pytest.mark.asyncio
    async def test_non_recursion_error(self, ctx):
        """Non-GraphRecursionError → returns False."""
        executor = _make_executor(ctx)
        msgs = [HumanMessage(content="test")]
        result = await executor._handle_iteration_limit(RuntimeError("other"), msgs)
        assert result is False


# ─── _handle_empty_response ──────────────────────────────────────────────────


class TestHandleEmptyResponse:
    @pytest.mark.asyncio
    async def test_empty_ai_response_injects_prompt(self, ctx):
        """Empty AI response triggers recovery prompt injection."""
        executor = _make_executor(ctx)
        collected = [
            HumanMessage(content="Hello"),
            AIMessage(content=""),
        ]

        result = await recover_empty_reply(executor, collected, retries=0)

        assert result is True
        messages = ctx.agent_input["messages"]
        last_msg = messages[-1]
        assert isinstance(last_msg, HumanMessage)
        assert "empty" in last_msg.content.lower()

    @pytest.mark.asyncio
    async def test_non_empty_response_no_injection(self, ctx):
        """AI response with content → returns False."""
        executor = _make_executor(ctx)
        collected = [
            HumanMessage(content="Hello"),
            AIMessage(content="Here is my response"),
        ]

        result = await recover_empty_reply(executor, collected, retries=0)
        assert result is False

    @pytest.mark.asyncio
    async def test_tool_call_response_no_injection(self, ctx):
        """AI response with tool calls → returns False."""
        executor = _make_executor(ctx)
        msg = AIMessage(content="")
        msg.tool_calls = [{"name": "search", "args": {}, "id": "tc1"}]
        collected = [HumanMessage(content="search"), msg]

        result = await recover_empty_reply(executor, collected, retries=0)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_response_exhausted_raises(self, ctx):
        """Retries exhausted → raises MyrmLLMError."""
        from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError

        executor = _make_executor(ctx)
        collected = [
            HumanMessage(content="Hello"),
            AIMessage(content=""),
        ]

        with pytest.raises(MyrmLLMError):
            await recover_empty_reply(executor, collected, retries=2)

    @pytest.mark.asyncio
    async def test_no_ai_message_returns_false(self, ctx):
        """No AI message in collected → returns False."""
        executor = _make_executor(ctx)
        collected = [HumanMessage(content="hello")]

        result = await recover_empty_reply(executor, collected, retries=0)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_response_emits_restart_recovery_event(self, ctx):
        """Recovery re-runs the turn from scratch → STATUS event carries restart."""
        executor = _make_executor(ctx)
        collected = [
            HumanMessage(content="Hello"),
            AIMessage(content=""),
        ]

        result = await recover_empty_reply(executor, collected, retries=0)

        assert result is True
        status_events = [
            e
            for e in executor._compactor.events
            if isinstance(e, dict) and e.get("type") == AgentEventType.STATUS.value
        ]
        assert any(e.get("step_key") == "empty_response_recovery" and e.get("restart") is True for e in status_events)
