"""A message the user sends into an existing chat lifts a Stop and restores the wake budget; nothing else does.

Checked against the real wake budget; the chat store is a stand-in.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service
from app.services.agent.params import AgentRequest
from app.services.agent.stream_session.chat_history_bootstrap import persist_user_message


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"human-{uuid.uuid4().hex[:8]}"
    get_adaptive_wakeup_service().record_user_stop(chat)
    yield chat
    get_adaptive_wakeup_service().reset_session(chat)


def request_for(chat_id: str, **overrides: object) -> AgentRequest:
    return AgentRequest.model_validate({"chat_id": chat_id, "message_id": "msg-1", "query": "continue", **overrides})


def stopped(chat_id: str) -> bool:
    return get_adaptive_wakeup_service().get_budget_state(chat_id).is_user_stopped


@pytest.fixture
def existing_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message",
        AsyncMock(return_value=SimpleNamespace(id="row-1")),
    )


@pytest.mark.asyncio
async def test_a_message_into_an_existing_chat_lifts_the_stop(chat_id: str, existing_chat: None) -> None:
    await persist_user_message(request_for(chat_id), text_content="continue")

    assert not stopped(chat_id)


@pytest.mark.asyncio
async def test_a_message_that_opens_a_new_chat_leaves_the_budget_alone(chat_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=None))

    await persist_user_message(request_for(chat_id), text_content="hello")

    assert stopped(chat_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"resume_value": {"approved": True}}, {"sibling_group_id": "group-1"}])
async def test_an_approval_resume_or_a_regenerate_is_not_a_new_message_from_the_user(
    chat_id: str, existing_chat: None, overrides: dict[str, object]
) -> None:
    await persist_user_message(request_for(chat_id, **overrides), text_content="continue")

    assert stopped(chat_id)
