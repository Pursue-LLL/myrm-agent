"""Fast Lane must not capture WebUI fast search (enable_web_search=True)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
    iter_agent_stream_chunks,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def _session(*, enable_web_search: bool) -> SimpleNamespace:
    return SimpleNamespace(
        request=SimpleNamespace(
            action_mode="fast",
            blueprint_id=None,
            mention_references=None,
            resume_value=None,
            ephemeral_subagents=None,
            use_workflow=False,
            chat_id=None,
        ),
        routing_tier="simple",
        params=SimpleNamespace(
            message_id="msg-fast-search-1",
            query="who is Guido van Rossum",
            enable_web_search=enable_web_search,
        ),
        cancel_token=SimpleNamespace(
            is_cancelled=False,
            cancel_reason=None,
            cancel=lambda *_args, **_kwargs: None,
        ),
        steering_token=None,
        extra_context={},
        stream_ttft_ms=None,
        stream_started_at_monotonic=0.0,
        research_model_cfg=None,
        collector=StreamContentCollector(chat_id=None),
        goal_provider=None,
    )


@pytest.mark.asyncio
async def test_fast_search_skips_fast_lane_when_web_search_enabled() -> None:
    session = _session(enable_web_search=True)

    async def _fake_agent_stream(**_: object):
        yield {"type": "message", "data": "search-agent"}

    with (
        patch(
            "app.services.agent.stream_session.stream_loop.create_fast_lane_stream",
            new_callable=AsyncMock,
        ) as fast_lane_mock,
        patch(
            "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
            side_effect=_fake_agent_stream,
        ) as agent_stream_mock,
        patch(
            "app.services.agent.stream_session.stream_loop.should_suggest_workflow_for_session",
            return_value=False,
        ),
    ):
        _ = [
            chunk
            async for chunk in iter_agent_stream_chunks(
                session,
                ApprovalTimeoutHolder(),
                ClarificationTimeoutHolder(),
            )
        ]

    fast_lane_mock.assert_not_called()
    agent_stream_mock.assert_called_once()


@pytest.mark.asyncio
async def test_fast_lane_used_for_fast_mode_without_web_search() -> None:
    session = _session(enable_web_search=False)

    async def _fake_fast_lane(*_: object):
        yield {"type": "message", "data": "fast-lane"}
        yield {"type": "message_end", "usage": {}}

    with (
        patch(
            "app.services.agent.stream_session.stream_loop.create_fast_lane_stream",
            side_effect=_fake_fast_lane,
        ) as fast_lane_mock,
        patch(
            "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
            new_callable=AsyncMock,
        ) as agent_stream_mock,
    ):
        _ = [
            chunk
            async for chunk in iter_agent_stream_chunks(
                session,
                ApprovalTimeoutHolder(),
                ClarificationTimeoutHolder(),
            )
        ]

    fast_lane_mock.assert_called_once()
    agent_stream_mock.assert_not_called()
