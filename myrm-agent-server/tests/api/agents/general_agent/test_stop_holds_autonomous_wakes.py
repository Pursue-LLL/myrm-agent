"""A Stop on a running turn also keeps the chat from waking itself, checked against the real gateway and registry.

Both Stop endpoints end the turn; what the user stopped must not restart on its own when a background task it
started settles later, so each also arms the chat's wake budget until the user writes again.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.responses import JSONResponse
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken

from app.api.agents.general_agent.streaming import cancel_active_chat_agent, cancel_agent_request
from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service
from app.services.agent.gateway import get_agent_gateway


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"stop-{uuid.uuid4().hex[:8]}"
    yield chat
    get_agent_gateway().release_session(chat)
    get_adaptive_wakeup_service().reset_session(chat)


@pytest.fixture
def running_turn(chat_id: str) -> Iterator[str]:
    """A chat turn as the stream pipeline sets it up: the chat is claimed under the message id, which has a token."""
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    get_agent_gateway().reserve_session(chat_id, active_message_id=message_id)
    CancellationRegistry.register(CancellationToken(request_id=message_id))
    yield message_id
    CancellationRegistry.unregister(message_id)


@pytest.fixture(autouse=True)
def mobile_gate_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.remote_access.mobile_gate.require_mobile_pair_chat_access", lambda *_args, **_kwargs: None)


def stopped(chat_id: str) -> bool:
    return get_adaptive_wakeup_service().get_budget_state(chat_id).is_user_stopped


def body_of(response: JSONResponse) -> dict[str, object]:
    body: dict[str, object] = json.loads(bytes(response.body))
    return body


@pytest.mark.asyncio
async def test_stopping_by_message_ends_the_turn_and_holds_the_chat_s_wakes(chat_id: str, running_turn: str) -> None:
    response = await cancel_agent_request(running_turn)

    assert body_of(response)["data"] == {"cancelled": True, "message_id": running_turn}
    assert CancellationRegistry.is_cancelled(running_turn)
    assert stopped(chat_id)


@pytest.mark.asyncio
async def test_stopping_by_chat_ends_the_turn_and_holds_the_chat_s_wakes(chat_id: str, running_turn: str) -> None:
    response = await cancel_active_chat_agent(chat_id, MagicMock())

    assert body_of(response)["data"] == {"cancelled": True, "chat_id": chat_id, "message_id": running_turn}
    assert CancellationRegistry.is_cancelled(running_turn)
    assert stopped(chat_id)


@pytest.mark.asyncio
async def test_a_stop_only_holds_the_chat_it_stopped(chat_id: str, running_turn: str) -> None:
    other = f"other-{uuid.uuid4().hex[:8]}"

    await cancel_agent_request(running_turn)

    assert not stopped(other)
    get_adaptive_wakeup_service().reset_session(other)


@pytest.mark.asyncio
async def test_a_stop_that_found_nothing_running_holds_nothing(chat_id: str) -> None:
    by_message = await cancel_agent_request("msg-nothing-runs-here")
    by_chat = await cancel_active_chat_agent(chat_id, MagicMock())

    assert body_of(by_message)["code"] == 404
    assert body_of(by_chat)["code"] == 404
    assert not stopped(chat_id)


@pytest.mark.asyncio
async def test_the_chat_of_a_running_message_is_found_through_the_gateway(chat_id: str, running_turn: str) -> None:
    gateway = get_agent_gateway()

    assert gateway.get_session_id_by_message(running_turn) == chat_id
    assert gateway.get_session_id_by_message("msg-nothing-runs-here") is None

    gateway.release_session(chat_id)
    assert gateway.get_session_id_by_message(running_turn) is None
