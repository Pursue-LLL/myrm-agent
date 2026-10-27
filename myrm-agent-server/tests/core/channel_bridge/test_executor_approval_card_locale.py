"""A channel run that stops at a tool approval shows the card in the language of the member who asked.

The card also names the channel session the run belongs to, so the answer resumes that session's chat.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.types import ApprovalExpiry, InboundMessage, ProgressUpdate
from app.core.channel_bridge.agent_executor.approval_card import build_approval_card
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor

_EXECUTOR = "app.core.channel_bridge.agent_executor.executor"
_SESSION_KEY = "telegram:dm:user-1:e=2026-10-26"
_APPROVAL_DATA: dict[str, object] = {
    "actionRequests": [{"action": "shell", "description": "run the build"}],
    "extensions": {"timeout": {"seconds": 120, "behavior": "deny"}},
}


class _ApprovalAgent:
    """Stops at an approval request, the way a graph does when it hits an interrupt."""

    async def process_stream(self, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "tool_approval_request", "data": _APPROVAL_DATA}


def _inbound(locale: str) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="Deploy it",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=False,
        mentioned=False,
        metadata={"locale": locale},
    )


def _prepared_run() -> SimpleNamespace:
    return SimpleNamespace(
        agent=_ApprovalAgent(),
        token_ctx=None,
        chat_id="chat-db",
        session_key=_SESSION_KEY,
        chat_history=[],
        query_input="hi",
        channel_budget_key="",
        memory_settings=None,
        lite_model_cfg=None,
        session_was_auto_reset=False,
        session_policy=None,
        params=SimpleNamespace(agent_id="main"),
        agent_engine_params={},
        user_timezone="UTC",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "ja", "zh-CN"])
async def test_the_approval_card_is_worded_for_the_sender(locale: str) -> None:
    prepared = SimpleNamespace(pre_events=[], prep=_prepared_run())

    with (
        patch(f"{_EXECUTOR}.prepare_channel_execution", AsyncMock(return_value=prepared)),
        patch("app.services.agent.runtime_context.build_agent_runtime_context", AsyncMock(return_value={})),
        patch(f"{_EXECUTOR}.finalize_channel_stream_reply", AsyncMock(return_value="reply")),
        patch(f"{_EXECUTOR}.finalize_agent_session", AsyncMock()),
    ):
        cards = [
            event
            async for event in ChannelAgentExecutor().execute_stream(_inbound(locale), cancel_token=CancellationToken())
            if isinstance(event, ProgressUpdate) and event.quick_replies
        ]

    (card,) = cards
    expected = build_approval_card(_APPROVAL_DATA, locale=locale, session_key=_SESSION_KEY)
    assert card.label == expected.label
    assert [q.label for q in card.quick_replies] == [q.label for q in expected.quick_replies]
    assert card.expiry == ApprovalExpiry(seconds=120, behavior="deny")
    assert card.session_key == _SESSION_KEY
