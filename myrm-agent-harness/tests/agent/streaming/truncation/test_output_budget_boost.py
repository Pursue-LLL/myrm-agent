"""The output budget a truncation retry runs with: scaling, ceilings, and the lifetime of the override."""

import asyncio
import contextlib
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.streaming.stream_executor import StreamContext
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.toolkits.llms.utils import model_utils

from .support import llm_with_max_tokens, make_executor

# ---------------------------------------------------------------------------
# ContextVar accessors
# ---------------------------------------------------------------------------


def test_contextvar_get_set_reset():
    """get/set/reset ephemeral_max_output_tokens ContextVar round-trip."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
        set_ephemeral_max_output_tokens,
    )

    assert get_ephemeral_max_output_tokens() is None

    set_ephemeral_max_output_tokens(8000)
    assert get_ephemeral_max_output_tokens() == 8000

    reset_ephemeral_max_output_tokens()
    assert get_ephemeral_max_output_tokens() is None


def test_contextvar_set_caps_at_max():
    """set_ephemeral_max_output_tokens caps at _MAX_EPHEMERAL_OUTPUT_TOKENS."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        _MAX_EPHEMERAL_OUTPUT_TOKENS,
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
        set_ephemeral_max_output_tokens,
    )

    set_ephemeral_max_output_tokens(999999)
    assert get_ephemeral_max_output_tokens() == _MAX_EPHEMERAL_OUTPUT_TOKENS
    reset_ephemeral_max_output_tokens()


# ---------------------------------------------------------------------------
# _boost_output_tokens with valid LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boost_output_tokens_progressive_scaling(mock_context):
    """_boost_output_tokens applies progressive scaling: 2x, 3x, 4x."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    llm_mock = MagicMock()
    llm_mock.max_tokens = 4000
    mock_context.llm = llm_mock
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() == 8000

    executor._boost_output_tokens(1)
    assert get_ephemeral_max_output_tokens() == 12000

    executor._boost_output_tokens(2)
    assert get_ephemeral_max_output_tokens() == 16000

    executor._boost_output_tokens(5)
    assert get_ephemeral_max_output_tokens() == 16000

    reset_ephemeral_max_output_tokens()


# ---------------------------------------------------------------------------
# _boost_output_tokens with no LLM / no max_tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boost_no_op_when_llm_is_none(mock_context):
    """_boost_output_tokens is a no-op when llm is None."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
    )

    mock_context.llm = None
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() is None


@pytest.mark.asyncio
async def test_boost_no_op_when_max_tokens_invalid(mock_context):
    """_boost_output_tokens is a no-op when max_tokens is 0 or negative."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
    )

    llm_mock = MagicMock()
    llm_mock.max_tokens = 0
    mock_context.llm = llm_mock
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() is None

    llm_mock.max_tokens = -1
    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() is None


# ---------------------------------------------------------------------------
# ContextVar cleanup in StreamExecutor finally block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ephemeral_contextvar_reset_after_execute():
    """ContextVar is always reset in StreamExecutor.execute's finally block."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        set_ephemeral_max_output_tokens,
    )

    set_ephemeral_max_output_tokens(16000)
    assert get_ephemeral_max_output_tokens() == 16000

    stats = AgentRunStatistics()
    ctx = StreamContext(
        agent=MagicMock(),
        agent_input={"messages": []},
        merged_context={},
        run_config={},
        stats=stats,
        message_id="test",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
    )
    executor = make_executor(ctx)

    ctx.agent.astream_events = MagicMock(side_effect=RuntimeError("test abort"))

    with contextlib.suppress(RuntimeError):
        await executor.execute()

    assert get_ephemeral_max_output_tokens() is None


# ---------------------------------------------------------------------------
# Boost cap: ensure 65536 ceiling even with large base
# ---------------------------------------------------------------------------


def test_boost_caps_at_65536():
    """_boost_output_tokens never exceeds MAX_EPHEMERAL_OUTPUT_TOKENS (65536)."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    stats = AgentRunStatistics()
    ctx = StreamContext(
        agent=None,
        agent_input={},
        merged_context={},
        run_config={},
        stats=stats,
        message_id="test",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
    )

    llm_mock = MagicMock()
    llm_mock.max_tokens = 16384
    ctx.llm = llm_mock

    executor = make_executor(ctx)
    executor._boost_output_tokens(2)

    val = get_ephemeral_max_output_tokens()
    assert val == 65536
    reset_ephemeral_max_output_tokens()


@pytest.mark.parametrize(
    ("configured", "expected_override"),
    [
        (40_000, 65536),
        (65536, None),
        (100_000, None),
    ],
)
def test_boost_never_lowers_a_configured_budget(
    mock_context: StreamContext, configured: int, expected_override: int | None
):
    """The override only raises the output budget; a budget that already reaches the cap is left as configured."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    mock_context.llm = llm_with_max_tokens(configured)
    executor = make_executor(mock_context)
    try:
        executor._boost_output_tokens(0)
        assert get_ephemeral_max_output_tokens() == expected_override
    finally:
        reset_ephemeral_max_output_tokens()


# ---------------------------------------------------------------------------
# _get_configured_max_tokens: model_kwargs fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boost_uses_model_kwargs_max_tokens(mock_context):
    """When llm.max_tokens is None but model_kwargs has max_tokens, boost works."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    llm_mock = MagicMock()
    llm_mock.max_tokens = None
    llm_mock.model_kwargs = {"max_tokens": 4096}
    mock_context.llm = llm_mock
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() == 8192  # 4096 × 2
    reset_ephemeral_max_output_tokens()


@pytest.mark.asyncio
async def test_boost_prefers_direct_max_tokens_over_model_kwargs(mock_context):
    """llm.max_tokens takes precedence over model_kwargs.max_tokens."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    llm_mock = MagicMock()
    llm_mock.max_tokens = 8000
    llm_mock.model_kwargs = {"max_tokens": 4096}
    mock_context.llm = llm_mock
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() == 16000  # 8000 × 2 (direct wins)
    reset_ephemeral_max_output_tokens()


@pytest.mark.asyncio
async def test_boost_no_op_when_model_kwargs_max_tokens_invalid(mock_context):
    """model_kwargs.max_tokens <= 0 is ignored, boost is no-op."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    reset_ephemeral_max_output_tokens()
    llm_mock = MagicMock()
    llm_mock.max_tokens = None
    llm_mock.model_kwargs = {"max_tokens": 0}
    mock_context.llm = llm_mock
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() is None


@pytest.mark.asyncio
async def test_boost_no_op_when_model_kwargs_empty(mock_context):
    """Empty model_kwargs means no fallback, boost is no-op."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    reset_ephemeral_max_output_tokens()
    llm_mock = MagicMock()
    llm_mock.max_tokens = None
    llm_mock.model_kwargs = {}
    mock_context.llm = llm_mock
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() is None


@pytest.mark.asyncio
async def test_thinking_boost_uses_model_headroom_floor(mock_context):
    """With no configured max_tokens, a thinking model boosts from its headroom floor."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    reset_ephemeral_max_output_tokens()
    llm_mock = MagicMock()
    llm_mock.max_tokens = None
    llm_mock.model_kwargs = {}
    llm_mock.model_name = "minimax/MiniMax-M3"
    mock_context.llm = llm_mock
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    # 16384 floor × 2 for the first retry.
    assert get_ephemeral_max_output_tokens() == 32768
    reset_ephemeral_max_output_tokens()


@pytest.mark.asyncio
async def test_boost_stays_noop_for_unknown_model_without_budget(mock_context):
    """Unknown model ceiling → no boost, avoiding an overshoot that would 400."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    reset_ephemeral_max_output_tokens()
    llm_mock = MagicMock()
    llm_mock.max_tokens = None
    llm_mock.model_kwargs = {}
    llm_mock.model_name = "some-unknown-model"
    mock_context.llm = llm_mock
    executor = make_executor(mock_context)

    executor._boost_output_tokens(0)
    assert get_ephemeral_max_output_tokens() is None


# ---------------------------------------------------------------------------
# Boost clamp: a retry never asks for more than the model's documented ceiling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("configured", "ceiling", "expected_override"),
    [
        (16384, 20_000, 20_000),  # ceiling between base and 2x becomes the boost
        (16384, 128_000, 32768),  # ceiling far above: the plain 2x boost
        (16384, 8192, None),  # ceiling below the base is a stale entry: base already served, no room to add
        (16384, 16384, None),  # base already sits on the ceiling
    ],
)
def test_boost_is_limited_to_the_model_ceiling(
    mock_context: StreamContext,
    monkeypatch: pytest.MonkeyPatch,
    configured: int,
    ceiling: int,
    expected_override: int | None,
):
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    monkeypatch.setattr(model_utils, "get_model_output_ceiling", lambda _model: ceiling)
    mock_context.llm = llm_with_max_tokens(configured)
    executor = make_executor(mock_context)
    try:
        executor._boost_output_tokens(0)
        assert get_ephemeral_max_output_tokens() == expected_override
    finally:
        reset_ephemeral_max_output_tokens()


def test_boost_stays_within_the_ceiling_on_later_retries(mock_context: StreamContext, monkeypatch: pytest.MonkeyPatch):
    """Retry levels scale up until the ceiling and then stay on it instead of overshooting."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        get_ephemeral_max_output_tokens,
        reset_ephemeral_max_output_tokens,
    )

    monkeypatch.setattr(model_utils, "get_model_output_ceiling", lambda _model: 40_000)
    mock_context.llm = llm_with_max_tokens(16384)
    executor = make_executor(mock_context)
    try:
        observed = []
        for retries in (0, 1, 2):
            executor._boost_output_tokens(retries)
            observed.append(get_ephemeral_max_output_tokens())
        assert observed == [32768, 40_000, 40_000]  # 2x fits; 3x and 4x are cut to the ceiling
    finally:
        reset_ephemeral_max_output_tokens()
