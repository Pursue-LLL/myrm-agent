"""Dynamic Workflow routing in stream_loop — no LLM required."""

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


def _session(*, use_workflow: bool) -> SimpleNamespace:
    return SimpleNamespace(
        request=SimpleNamespace(
            action_mode="agent",
            blueprint_id=None,
            mention_references=None,
            resume_value=None,
            ephemeral_subagents=None,
            use_workflow=use_workflow,
            chat_id="chat-dw-route",
            incognito_mode=False,
        ),
        routing_tier="complex",
        params=SimpleNamespace(
            message_id="msg-dw-route",
            query="audit apis",
            enable_web_search=False,
            enable_wiki=False,
            incognito_mode=False,
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
        collector=StreamContentCollector(chat_id="chat-dw-route"),
        goal_provider=None,
    )


@pytest.mark.asyncio
async def test_use_workflow_true_routes_to_dynamic_workflow_stream() -> None:
    session = _session(use_workflow=True)

    async def _fake_dw_stream(*_args, **_kwargs):
        yield {"type": "status", "step_key": "workflow_init", "status": "success", "data": {}}
        yield {"type": "message_end", "usage": {}}

    with (
        patch(
            "app.services.agent.stream_session.stream_lane_factory.create_dynamic_workflow_stream",
            side_effect=_fake_dw_stream,
        ) as dw_mock,
        patch(
            "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
            new_callable=AsyncMock,
        ) as agent_stream_mock,
    ):
        chunks = [
            chunk
            async for chunk in iter_agent_stream_chunks(
                session,
                ApprovalTimeoutHolder(),
                ClarificationTimeoutHolder(),
            )
        ]

    dw_mock.assert_called_once()
    agent_stream_mock.assert_not_called()
    assert any(
        isinstance(chunk, str) and "workflow_init" in chunk
        for chunk in chunks
    )


@pytest.mark.asyncio
async def test_use_workflow_false_does_not_route_to_dynamic_workflow_stream() -> None:
    session = _session(use_workflow=False)

    async def _fake_agent_stream(**_kwargs):
        yield {"type": "message", "data": "ok"}
        yield {"type": "message_end", "usage": {}}

    with (
        patch(
            "app.services.agent.stream_session.stream_lane_factory.create_dynamic_workflow_stream",
            new_callable=AsyncMock,
        ) as dw_mock,
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

    dw_mock.assert_not_called()
    agent_stream_mock.assert_called_once()
