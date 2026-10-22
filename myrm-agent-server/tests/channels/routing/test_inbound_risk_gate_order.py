"""The inbound risk gate sees what the sender typed on every path to an agent, and a message it holds leaves nothing behind.

Runs the real ``AgentRouter`` consume loop and ``_handle_merged`` against a real SQLite inbound journal.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.reliability.inbound_journal import SqliteInboundJournal
from app.channels.routing.command_defs import CommandKind
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_keys import routing_session_key
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

from .risk_gate_testkit import make_bus, make_router

_DETECTION = "app.services.risk.detection.get_detection_service"


@pytest.fixture
def journal(tmp_path: Path):
    store = SqliteInboundJournal(tmp_path / "journal.db")
    yield store
    store.close()


def _journaled_router(journal: SqliteInboundJournal) -> AgentRouter:
    router = make_router(make_bus())
    router.set_inbound_journal(journal)
    return router


@pytest.mark.asyncio
async def test_held_message_is_acknowledged_in_the_journal(journal: SqliteInboundJournal) -> None:
    """A held secret must not stay in the journal, where a restart would replay it."""
    router = _journaled_router(journal)
    msg = InboundMessage(channel="telegram", sender_id="u1", content=f"my key {SECRET}")

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await router._handle_merged(msg)

    router._bus.publish_outbound.assert_awaited_once()
    assert journal.scan_pending() == []


@pytest.mark.asyncio
async def test_topic_bind_command_is_acknowledged_in_the_journal(journal: SqliteInboundJournal) -> None:
    """A bind command returns before the agent turn; its journal entry would otherwise be replayed after a restart."""
    router = _journaled_router(journal)
    router._registry = MagicMock()
    router._registry.resolve.return_value = SimpleNamespace(
        command_def=SimpleNamespace(kind=CommandKind.AGENT_ROUTE, agent_id="agent-1", name="agent-1"),
        raw_args="",
    )
    router._handle_topic_command = AsyncMock()
    msg = InboundMessage(channel="telegram", sender_id="u1", content="/agent-1")

    with patch(_DETECTION, return_value=build_service_with_rules([])):
        await router._handle_merged(msg)
    await asyncio.sleep(0)

    router._handle_topic_command.assert_awaited_once()
    assert journal.scan_pending() == []


@pytest.mark.asyncio
async def test_secret_in_a_paste_the_guard_would_spill_is_held_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stub of 800 characters would hide the secret; the gate reads the paste before the context guard shortens it."""
    from app.services.agent.context_guard_service import ContextGuardService

    spill = AsyncMock()
    monkeypatch.setattr(ContextGuardService, "guard_inbound_prompt", spill)
    router = make_router()
    paste = "ordinary log line\n" * 1500 + f"key {SECRET}\n"
    assert len(paste) > 16_000

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await router._handle_merged(InboundMessage(channel="slack", sender_id="u1", content=paste))

    router._bus.publish_outbound.assert_awaited_once()
    spill.assert_not_awaited()


def _running_agent(router: AgentRouter, mode: str | None) -> SteeringToken:
    chat_id = "chat-1"
    token = SteeringToken()
    router._active_tasks[routing_session_key("telegram", chat_id)] = _ActiveTask(
        task=asyncio.current_task(),
        cancel_token=CancellationToken(),
        channel="telegram",
        chat_id=chat_id,
        placeholder_id=None,
        started_at=0.0,
        steering_token=token,
        busy_input_mode=mode,
    )
    return token


async def _consume_one(router: AgentRouter, msg: InboundMessage) -> None:
    router._running = True
    router._bus.consume_inbound = AsyncMock(side_effect=[msg, asyncio.CancelledError])
    await router._consume_loop()


def _typed(content: str, message_id: str = "m1") -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="chat-1", content=content, message_id=message_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["steer", "redirect"])
async def test_secret_typed_while_the_agent_runs_is_held_not_steered(mode: str) -> None:
    router = make_router()
    token = _running_agent(router, mode)

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await _consume_one(router, _typed(f"use {SECRET} instead"))

    assert not token.has_pending
    router._bus.publish_outbound.assert_awaited_once()


@pytest.mark.asyncio
async def test_clean_text_typed_while_the_agent_runs_still_steers() -> None:
    router = make_router()
    token = _running_agent(router, "steer")

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await _consume_one(router, _typed("only keep the 2026 rows"))

    assert token.activate() == ["only keep the 2026 rows"]


@pytest.mark.asyncio
async def test_slash_steer_with_a_secret_is_held() -> None:
    router = make_router()
    token = _running_agent(router, None)
    router._check_admin_permission = AsyncMock(return_value=True)

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await _consume_one(router, _typed(f"/steer use {SECRET} instead"))
        await _consume_one(router, _typed("/steer only keep the 2026 rows", message_id="m2"))
        await asyncio.sleep(0)

    assert token.activate() == ["only keep the 2026 rows"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "/background",
        "/bg steer task-1",
        "/btw",
        "/goal",
        "/subgoal",
        "/kanban comment card-1",
        "/learn",
        "/steer",
    ],
)
async def test_system_command_text_with_a_secret_is_held_before_it_acts(command: str) -> None:
    """A system command acts on its text directly, so the dispatcher screens it once for every one of them."""
    router = make_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    acted = AsyncMock(return_value=True)
    router._dispatch_system_command = acted
    msg = _typed(f"{command} use {SECRET} instead")

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        consumed = await router._dispatch_resolved(msg, router._registry.resolve(msg.content))

    assert consumed is True
    acted.assert_not_awaited()
    router._bus.publish_outbound.assert_awaited_once()


@pytest.mark.asyncio
async def test_system_command_with_clean_text_is_dispatched() -> None:
    router = make_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    acted = AsyncMock(return_value=True)
    router._dispatch_system_command = acted
    msg = _typed("/background summarise the 2026 rows")

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        consumed = await router._dispatch_resolved(msg, router._registry.resolve(msg.content))

    assert consumed is True
    acted.assert_awaited_once()
    router._bus.publish_outbound.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "spawned", "steered"),
    [
        (f"/background fetch with {SECRET}", False, False),
        (f"/background steer task-1 use {SECRET}", False, False),
        ("/background summarise the 2026 rows", True, False),
        ("/background steer task-1 only the 2026 rows", False, True),
    ],
)
async def test_background_command_reaches_its_handler_only_when_clean(text: str, spawned: bool, steered: bool) -> None:
    router = make_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    handler = MagicMock()
    handler.spawn_background = AsyncMock()
    handler.steer_background = AsyncMock()
    router._background_handler = handler
    msg = _typed(text)

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await router._dispatch_resolved(msg, router._registry.resolve(msg.content))
        await asyncio.sleep(0)

    assert handler.spawn_background.await_count == int(spawned)
    assert handler.steer_background.await_count == int(steered)


@pytest.mark.asyncio
async def test_secret_steering_a_delegated_task_is_held() -> None:
    router = make_router()
    router._delegation_coordinator = MagicMock()
    router._delegation_coordinator.find_active_task.return_value = SimpleNamespace(task_id="t-1")
    router._check_admin_permission = AsyncMock(return_value=True)

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await _consume_one(router, _typed(f"also use {SECRET}"))

    router._delegation_coordinator.inject_steering.assert_not_called()
    router._bus.publish_outbound.assert_awaited_once()


@pytest.mark.asyncio
async def test_secret_in_a_delegation_prompt_is_held() -> None:
    router = make_router()
    router._check_admin_permission = AsyncMock(return_value=True)
    router._handle_delegation_inbound = AsyncMock(return_value=True)

    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await _consume_one(router, _typed(f"/delegate call the API with {SECRET}"))

    router._handle_delegation_inbound.assert_not_awaited()
    router._bus.publish_outbound.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "spawned"), [(f"deploy now, key {SECRET}", 0), ("deploy now", 1)])
async def test_event_trigger_job_starts_only_for_a_message_the_gate_lets_through(text: str, spawned: int) -> None:
    """The consume loop dispatches event triggers before the turn path screens the message, so the dispatch screens it too."""
    router = make_router()
    router._is_sender_admitted = AsyncMock(return_value=True)
    router._is_untrusted_event_sender = AsyncMock(return_value=False)
    scheduler = MagicMock()
    scheduler.dispatch_event = AsyncMock(return_value=1)

    with (
        patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])),
        patch("app.core.cron.adapters.setup.get_cron_scheduler", return_value=scheduler),
        patch.object(router._gate, "submit"),
    ):
        await _consume_one(router, _typed(text))

    assert scheduler.dispatch_event.await_count == spawned


@pytest.mark.asyncio
async def test_held_message_leaves_one_hit_record_across_the_dispatch_and_the_turn() -> None:
    """The dispatch and the turn path both screen the message; only the turn path records, so the hit is counted once."""
    router = make_router()
    router._is_sender_admitted = AsyncMock(return_value=True)
    router._is_untrusted_event_sender = AsyncMock(return_value=False)
    service = build_service_with_rules([API_KEY_RULE])
    service.record_hits = AsyncMock()
    scheduler = MagicMock()
    scheduler.dispatch_event = AsyncMock(return_value=0)
    msg = _typed(f"key {SECRET}")

    @asynccontextmanager
    async def database_session() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    with (
        patch(_DETECTION, return_value=service),
        patch("app.platform_utils.get_session_factory", return_value=database_session),
        patch("app.core.cron.adapters.setup.get_cron_scheduler", return_value=scheduler),
        patch.object(router._gate, "submit"),
    ):
        await _consume_one(router, msg)
        assert service.record_hits.await_count == 0
        await router._handle_merged(msg)

    assert service.record_hits.await_count == 1
