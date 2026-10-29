"""The wake turn streams to the chat under the caller's lease, and a Stop ends it like it ends a chat turn.

Checked against the real gateway, cancellation registry and stream collector; the agent is a scripted stand-in (it
needs a model), and so are the stores, the event bus and the pooled-session release.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken, CancelReason

from app.services.agent.adaptive_wakeup import wake_turn_stream
from app.services.agent.adaptive_wakeup.wake_turn_stream import WAKE_TURN_FAILED_ERROR_KIND, stream_wake_turn
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.turn_lease import server_turn_lease

Events = list[dict[str, object]]


class ScriptedAgent:
    """Stands in for the general agent: each ``process_stream`` call plays the next script."""

    def __init__(self, *scripts: Callable[[CancellationToken], AsyncIterator[dict[str, object]]]) -> None:
        self._scripts = list(scripts)
        self.calls: list[dict[str, object]] = []

    def process_stream(self, **kwargs: object) -> AsyncIterator[dict[str, object]]:
        self.calls.append(kwargs)
        token = kwargs["cancel_token"]
        assert isinstance(token, CancellationToken)
        return self._scripts[min(len(self.calls), len(self._scripts)) - 1](token)


class FakeParams:
    chat_history: list[object] = []
    query = "[SYSTEM WAKEUP]"
    timezone = "UTC"
    force_external_agent = False
    agent_id = "agent-1"
    memory_channel_id: str | None = None

    def __init__(self, chat_id: str, message_id: str) -> None:
        self.chat_id = chat_id
        self.message_id = message_id

    def model_copy(self, update: dict[str, object]) -> FakeParams:
        return self


def message(text: str) -> dict[str, object]:
    return {"type": "message", "data": text}


async def plays(*events: dict[str, object]) -> AsyncIterator[dict[str, object]]:
    for event in events:
        yield event


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"stream-{uuid.uuid4().hex[:8]}"
    yield chat
    get_agent_gateway().release_session(chat)


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> Events:
    """Every chunk the wake turn put on the event bus for the chat."""
    chunks: Events = []
    bus = MagicMock()
    bus.publish.side_effect = lambda event: chunks.append({"session_id": event.data["session_id"], **event.data["chunk"]})
    monkeypatch.setattr("app.services.event.app_event_bus.get_event_bus", lambda: bus)
    return chunks


@pytest.fixture
def stores(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The stores and builders around the agent; nothing here needs a model or a database."""
    persisted = AsyncMock()
    finalized = AsyncMock()
    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        AsyncMock(return_value=SimpleNamespace(agent_id="agent-1", is_incognito=False)),
    )
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.load_web_chat_history", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", persisted)
    monkeypatch.setattr(wake_turn_stream, "convert_chat_history", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.agent.runtime_context.build_agent_runtime_context", AsyncMock(return_value={}))
    monkeypatch.setattr("app.services.agent.execution_cache.finalize_agent_session", finalized)

    @contextlib.asynccontextmanager
    async def no_credentials(**_kwargs: object) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr("app.services.agent.session_credential_assembler.session_credentials_scope", no_credentials)

    requests: list[SimpleNamespace] = []

    async def convert(request: SimpleNamespace, _history: object) -> tuple[FakeParams, None, None, None, list[str], list[object]]:
        requests.append(request)
        return FakeParams(request.chat_id, request.message_id), None, None, None, [], []

    monkeypatch.setattr("app.services.agent.params.convert_to_general_agent_params", convert)

    real_sleep = asyncio.sleep

    async def instant_retry(_seconds: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", instant_retry)
    return SimpleNamespace(persisted=persisted, finalized=finalized, requests=requests)


def use_agent(monkeypatch: pytest.MonkeyPatch, agent: ScriptedAgent) -> None:
    monkeypatch.setattr("app.ai_agents.AgentFactory.create_general_agent", staticmethod(lambda _params: agent))


async def run_wake_turn(chat_id: str, turn_id: str) -> None:
    async with server_turn_lease(chat_id, turn_id) as token:
        await stream_wake_turn(chat_id, turn_id, token)


@pytest.mark.asyncio
async def test_the_turn_streams_to_the_chat_under_the_lease_it_was_given(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    gateway = get_agent_gateway()
    seen_while_running: list[tuple[bool, str | None]] = []

    async def script(_token: CancellationToken) -> AsyncIterator[dict[str, object]]:
        seen_while_running.append((gateway.is_session_active(chat_id), gateway.get_active_message_id(chat_id)))
        yield message("done")

    agent = ScriptedAgent(script)
    use_agent(monkeypatch, agent)

    await run_wake_turn(chat_id, "turn-1")

    assert published == [{"session_id": chat_id, **message("done")}]
    # Stop finds the turn by chat id (gateway) and by turn id (registry); the stream runs under the token it flips.
    assert seen_while_running == [(True, "turn-1")]
    call = agent.calls[0]
    assert (call["chat_id"], call["message_id"]) == (chat_id, "turn-1")
    assert isinstance(call["cancel_token"], CancellationToken)
    assert call["cancel_token"].request_id == "turn-1"
    stores.persisted.assert_awaited_once()
    assert stores.persisted.await_args.args[:2] == (chat_id, "done")
    stores.finalized.assert_awaited_once()
    assert not gateway.is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_stop_ends_the_turn_with_agent_cancelled_and_keeps_what_was_said(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    async def script(_token: CancellationToken) -> AsyncIterator[dict[str, object]]:
        yield message("partial")
        # The Stop arrives between two events; the second must never reach the chat.
        assert CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)
        yield message("never shown")

    agent = ScriptedAgent(script)
    use_agent(monkeypatch, agent)

    await run_wake_turn(chat_id, "turn-1")

    assert published == [
        {"session_id": chat_id, **message("partial")},
        {
            "session_id": chat_id,
            "type": "agent_cancelled",
            "messageId": "turn-1",
            "data": {"reason": "user_cancelled"},
        },
    ]
    assert len(agent.calls) == 1
    assert stores.persisted.await_args.args[:2] == (chat_id, "partial")
    stores.finalized.assert_awaited_once()
    # The stream was closed, not left suspended, so the chat is free the moment the turn ends.
    assert not get_agent_gateway().is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_run_that_ends_on_its_own_after_a_stop_still_reports_the_stop(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    async def script(_token: CancellationToken) -> AsyncIterator[dict[str, object]]:
        CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)
        return
        yield  # pragma: no cover - makes this an async generator

    use_agent(monkeypatch, ScriptedAgent(script))

    await run_wake_turn(chat_id, "turn-1")

    assert [chunk["type"] for chunk in published] == ["agent_cancelled"]


@pytest.mark.asyncio
async def test_a_stopped_turn_is_not_started_over_when_it_fails_on_the_way_out(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    async def script(_token: CancellationToken) -> AsyncIterator[dict[str, object]]:
        CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)
        raise RuntimeError("tool torn down")
        yield  # pragma: no cover - makes this an async generator

    agent = ScriptedAgent(script)
    use_agent(monkeypatch, agent)

    await run_wake_turn(chat_id, "turn-1")

    assert len(agent.calls) == 1
    stores.finalized.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failed_run_that_said_nothing_is_retried_and_only_the_last_attempt_is_kept(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    async def failing(_token: CancellationToken) -> AsyncIterator[dict[str, object]]:
        raise RuntimeError("provider hiccup")
        yield  # pragma: no cover - makes this an async generator

    agent = ScriptedAgent(failing, lambda _token: plays(message("second try")))
    use_agent(monkeypatch, agent)

    await run_wake_turn(chat_id, "turn-1")

    assert len(agent.calls) == 2
    assert [chunk["data"] for chunk in published] == ["second try"]
    assert stores.persisted.await_args.args[:2] == (chat_id, "second try")


@pytest.mark.asyncio
async def test_a_run_that_keeps_failing_ends_in_an_error_event_and_an_error_reply_instead_of_silence(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    async def failing(_token: CancellationToken) -> AsyncIterator[dict[str, object]]:
        raise RuntimeError("provider down")
        yield  # pragma: no cover - makes this an async generator

    agent = ScriptedAgent(failing)
    use_agent(monkeypatch, agent)

    await run_wake_turn(chat_id, "turn-1")

    assert len(agent.calls) == 3
    assert [chunk["type"] for chunk in published] == ["error"]
    assert published[0]["error_kind"] == WAKE_TURN_FAILED_ERROR_KIND
    assert published[0]["messageId"] == "turn-1"
    # The reply row is what a reload shows, so the failure outlives the open chat.
    stores.persisted.assert_awaited_once()
    assert stores.persisted.await_args.args[:2] == (chat_id, "")
    assert stores.persisted.await_args.kwargs["extra_data"]["completionStatus"] == "error"
    stores.finalized.assert_awaited_once()
    assert not get_agent_gateway().is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_run_that_fails_after_it_said_something_is_not_started_over_so_nothing_is_shown_twice(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    async def breaks_midway(_token: CancellationToken) -> AsyncIterator[dict[str, object]]:
        yield message("first half")
        raise RuntimeError("stream cut")

    agent = ScriptedAgent(breaks_midway, lambda _token: plays(message("never started")))
    use_agent(monkeypatch, agent)

    await run_wake_turn(chat_id, "turn-1")

    assert len(agent.calls) == 1
    assert [chunk["type"] for chunk in published] == ["message", "error"]
    assert stores.persisted.await_args.args[:2] == (chat_id, "first half")
    assert stores.persisted.await_args.kwargs["extra_data"]["completionStatus"] == "error"


@pytest.mark.asyncio
async def test_a_chat_that_is_gone_gets_no_wake_turn(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=None))
    agent = ScriptedAgent(lambda _token: plays(message("never")))
    use_agent(monkeypatch, agent)

    await run_wake_turn(chat_id, "turn-1")

    assert agent.calls == []
    assert published == []
    stores.persisted.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_turn_belongs_to_the_agent_the_chat_is_bound_to(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace
) -> None:
    use_agent(monkeypatch, ScriptedAgent(lambda _token: plays(message("done"))))

    await run_wake_turn(chat_id, "turn-1")

    assert [(request.chat_id, request.agent_id) for request in stores.requests] == [(chat_id, "agent-1")]


@pytest.mark.asyncio
@pytest.mark.parametrize("incognito", [True, False])
async def test_the_turn_keeps_the_incognito_flag_of_the_chat_it_wakes(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, published: Events, stores: SimpleNamespace, incognito: bool
) -> None:
    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        AsyncMock(return_value=SimpleNamespace(agent_id="agent-1", is_incognito=incognito)),
    )
    use_agent(monkeypatch, ScriptedAgent(lambda _token: plays(message("done"))))

    await run_wake_turn(chat_id, "turn-1")

    assert [request.incognito_mode for request in stores.requests] == [incognito]
