"""The turn crash auto-continue replays takes its chat and a registered cancel token before it builds its agent.

Checked against the real gateway and cancellation registry; the agent stream, chat persistence and notifications are
stand-ins. The chat Stop button and the emergency stop reach a replayed turn through that chat claim and that token,
and a chat a message took first is not replayed on top of it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken, CancelReason

from app.lifecycle.auto_continue import _dispatch_auto_continue
from app.services.agent.gateway import get_agent_gateway

_MARKER_ID = "marker-lease"
_TURN_ID = f"auto_continue_{_MARKER_ID}"


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"auto-lease-{uuid.uuid4().hex[:8]}"
    yield chat
    # The gateway is one per process: a failing test must not leave its chat busy for the next one.
    get_agent_gateway().release_session(chat)


def _marker(chat: str) -> MagicMock:
    marker = MagicMock()
    marker.id = _MARKER_ID
    marker.chat_id = chat
    marker.user_message_id = "msg-user"
    marker.attempt_count = 0
    marker.pending_steering_messages = None
    marker.created_at = datetime.now(UTC)
    marker.serialized_params = {"chat_id": chat, "query": "hello", "model_cfg": {"provider": "test", "model": "m"}}
    return marker


@contextmanager
def _replay_environment(chat: str, stream: Callable[..., AsyncIterator[object]]) -> Iterator[tuple[AsyncMock, MagicMock]]:
    """Everything ``_dispatch_auto_continue`` touches around the agent stream, with ``stream`` as the agent.

    Yields the notification sender and the registry that ends a stopped turn's background jobs.
    """
    factory = MagicMock()
    db = AsyncMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    registry = MagicMock()
    registry.kill_session_jobs = AsyncMock(return_value=0)
    notify = AsyncMock()
    with ExitStack() as stack:
        stack.enter_context(patch("app.platform_utils.get_session_factory", return_value=factory))
        params_cls = stack.enter_context(patch("app.ai_agents.GeneralAgentParams"))
        params_cls.model_validate.return_value = MagicMock(model_cfg=MagicMock(), chat_id=chat, timezone="UTC")
        stack.enter_context(patch("app.services.agent.streaming.ai_agent_service_stream", side_effect=stream))
        stack.enter_context(
            patch("app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots", AsyncMock(return_value=[]))
        )
        stack.enter_context(patch("app.services.chat.chat_service.ChatService.load_web_chat_history", AsyncMock(return_value=[])))
        stack.enter_context(patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", AsyncMock()))
        stack.enter_context(patch("app.services.infra.system_notification.SystemNotificationService.create_notification", notify))
        stack.enter_context(patch("myrm_agent_harness.api.hooks.get_background_registry", return_value=registry))
        yield notify, registry


async def _replay(chat: str, stream: Callable[..., AsyncIterator[object]]) -> tuple[AsyncMock, MagicMock]:
    with _replay_environment(chat, stream) as (notify, registry):
        await _dispatch_auto_continue(_marker(chat), MagicMock())
    return notify, registry


@pytest.mark.asyncio
async def test_the_replay_holds_its_chat_and_a_registered_cancel_token_while_it_runs(chat_id: str) -> None:
    seen: dict[str, object] = {}

    async def stream(**kwargs: object) -> AsyncIterator[dict[str, object]]:
        gateway = get_agent_gateway()
        seen["token"] = kwargs.get("cancel_token")
        seen["chat_active"] = gateway.is_session_active(chat_id)
        seen["turn_id"] = gateway.get_active_message_id(chat_id)
        # A stop finds the replay by its id: the registered token is the one the stream runs under.
        seen["stop_reached_it"] = CancellationRegistry.cancel(_TURN_ID, CancelReason.USER_CANCELLED)
        yield {"type": "message_end"}

    await _replay(chat_id, stream)

    token = seen["token"]
    assert isinstance(token, CancellationToken)
    assert token.request_id == _TURN_ID
    assert token.is_cancelled
    assert seen["chat_active"] is True
    assert seen["turn_id"] == _TURN_ID
    assert seen["stop_reached_it"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True], ids=["ran_to_the_end", "failed"])
async def test_the_replay_gives_back_its_chat_and_token_however_it_ends(chat_id: str, fails: bool) -> None:
    async def stream(**_kwargs: object) -> AsyncIterator[dict[str, object]]:
        if fails:
            raise RuntimeError("agent could not be created")
        yield {"type": "message_end"}

    notify, _registry = await _replay(chat_id, stream)

    assert not get_agent_gateway().is_session_active(chat_id)
    assert not CancellationRegistry.cancel(_TURN_ID, CancelReason.USER_CANCELLED)
    assert [call.kwargs["type"] for call in notify.await_args_list] == ["error" if fails else "success"]


@pytest.mark.asyncio
async def test_a_stopped_replay_ends_the_background_jobs_it_started(chat_id: str) -> None:
    async def stream(**_kwargs: object) -> AsyncIterator[dict[str, object]]:
        CancellationRegistry.cancel(_TURN_ID, CancelReason.ESTOP)
        yield {"type": "message_end"}

    _notify, registry = await _replay(chat_id, stream)

    registry.kill_session_jobs.assert_awaited_once_with(chat_id)


@pytest.mark.asyncio
async def test_a_chat_a_message_took_first_is_not_replayed_on_top_of_it(chat_id: str) -> None:
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-message")
    calls: list[object] = []

    async def stream(**_kwargs: object) -> AsyncIterator[dict[str, object]]:
        calls.append(1)
        yield {"type": "message_end"}

    notify, _registry = await _replay(chat_id, stream)

    assert calls == []
    assert gateway.get_active_message_id(chat_id) == "user-message"
    assert [call.kwargs["type"] for call in notify.await_args_list] == ["error"]
