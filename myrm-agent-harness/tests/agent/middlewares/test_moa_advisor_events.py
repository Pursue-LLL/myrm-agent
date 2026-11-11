"""The events the advisor round sends to the stream while it runs."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
    _emit_overlay_active,
    _emit_overlay_skipped,
    _emit_ref_done,
    create_moa_advisor_middleware,
)
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAOverlayConfig
from myrm_agent_harness.toolkits.llms.consensus.types import ReferenceResponse
from myrm_agent_harness.utils.runtime.progress_sink import set_tool_progress_sink

_RUN = "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run"


class _Sink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def emit(self, event: dict[str, object]) -> None:
        self.events.append(event)


@pytest.fixture
def sink() -> Iterator[_Sink]:
    collected = _Sink()
    set_tool_progress_sink(collected)
    yield collected
    set_tool_progress_sink(None)


async def _ask_through(config: MoAOverlayConfig) -> AsyncMock:
    """Send one fresh user turn through the middleware and return the handler it ended up calling."""
    llm = MagicMock(model_name="ref-a")
    middleware = create_moa_advisor_middleware([llm], config=config)
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    await middleware.awrap_model_call(request, handler)
    return handler


@pytest.mark.asyncio
async def test_a_finished_reference_is_reported_with_its_answer(sink: _Sink) -> None:
    await _emit_ref_done("ref-a", success=True, elapsed=0.5, content="advice")

    assert sink.events == [
        {
            "type": "status",
            "step_key": "moa_ref_done",
            "data": {"model": "ref-a", "success": True, "elapsed": 0.5, "content": "advice"},
        }
    ]


@pytest.mark.asyncio
async def test_the_round_names_its_references_and_what_triggered_it(sink: _Sink) -> None:
    await _emit_overlay_active(["ref-a", "ref-b"])
    await _emit_overlay_active(["ref-a"], trigger_reason="error_streak")

    assert {event["step_key"] for event in sink.events} == {"moa_overlay_active"}
    assert [event["data"] for event in sink.events] == [
        {"reference_models": ["ref-a", "ref-b"]},
        {"reference_models": ["ref-a"], "trigger_reason": "error_streak"},
    ]


@pytest.mark.asyncio
async def test_a_skipped_round_says_why(sink: _Sink) -> None:
    await _emit_overlay_skipped("budget_pressure")

    assert sink.events == [
        {
            "type": "status",
            "step_key": "moa_overlay_skipped",
            "status": "warning",
            "data": {"reason": "budget_pressure"},
        }
    ]


@pytest.mark.asyncio
async def test_a_round_the_stream_was_never_told_about_is_not_reported_as_timed_out(sink: _Sink) -> None:
    async def hang(*_args: object, **_kwargs: object) -> list[ReferenceResponse]:
        await asyncio.sleep(0.5)
        return []

    with patch(_RUN, side_effect=hang):
        handler = await _ask_through(MoAOverlayConfig(fanout="every_n", every_n=2, timeout_total=0.01))

    handler.assert_awaited_once()
    assert sink.events == []


@pytest.mark.asyncio
async def test_a_round_the_stream_was_never_told_about_is_not_reported_as_short_of_advice(sink: _Sink) -> None:
    failed = ReferenceResponse(model="ref-a", content="", elapsed_seconds=0.1, success=False, error="overloaded")

    with patch(_RUN, new_callable=AsyncMock, return_value=[failed]):
        handler = await _ask_through(MoAOverlayConfig(fanout="every_n", every_n=2, min_successful=1))

    handler.assert_awaited_once()
    assert sink.events == []


@pytest.mark.asyncio
async def test_emit_ref_done_no_sink_is_noop() -> None:
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        _emit_ref_done,
    )

    with patch(
        "myrm_agent_harness.utils.runtime.progress_sink.get_tool_progress_sink",
        return_value=None,
    ):
        await _emit_ref_done("ref-a", success=True, elapsed=0.1, content="x")


@pytest.mark.asyncio
async def test_emit_overlay_active_no_sink_is_noop() -> None:
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        _emit_overlay_active,
    )

    with patch(
        "myrm_agent_harness.utils.runtime.progress_sink.get_tool_progress_sink",
        return_value=None,
    ):
        await _emit_overlay_active(["ref-a"])


@pytest.mark.asyncio
async def test_emit_overlay_skipped_no_sink_is_noop() -> None:
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        _emit_overlay_skipped,
    )

    with patch(
        "myrm_agent_harness.utils.runtime.progress_sink.get_tool_progress_sink",
        return_value=None,
    ):
        await _emit_overlay_skipped("budget_pressure")
