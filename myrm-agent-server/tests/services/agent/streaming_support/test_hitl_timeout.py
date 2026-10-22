"""HITL timeout auto-resume against the real harness scheduler and the real gateway.

The scheduler fires, the resume callback runs a suspending agent stream through ``AgentGateway.execute_stream``,
and the next interrupt is armed or reopened. Only the agent stream's events and chat persistence are faked.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.types import Command
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.execution_cache.types import ExecutionMode
from app.services.agent.gateway import AgentGateway, GatewayConfig
from app.services.agent.streaming_support import hitl_timeout
from app.services.agent.streaming_support.hitl_timeout import (
    CLARIFICATION_NO_ANSWER_RESUME_VALUE,
    CLARIFICATION_TIMEOUT_SECONDS,
    HitlKind,
    arm_interrupt_timeout,
    schedule_approval_timeout,
    schedule_clarification_timeout,
)

CHAT_ID = "chat-hitl"
FAST = 0.02

CLARIFICATION_EVENT: dict[str, object] = {
    "type": "clarification_required",
    "data": {"type": "ask_question", "form": {"questions": []}},
}
APPROVAL_EVENT: dict[str, object] = {
    "type": "tool_approval_request",
    "data": {"extensions": {"timeout": {"seconds": 600, "behavior": "deny"}}},
}
UNARMED_EVENT: dict[str, object] = {"type": "approval_required", "data": {"type": "plan_confirm"}}
MESSAGE_EVENT: dict[str, object] = {"type": "message", "data": "continued"}

StreamFactory = Callable[..., AsyncGenerator[dict[str, object], None]]


@pytest.fixture(autouse=True)
def _fresh_scheduler() -> Iterator[None]:
    ApprovalTimeoutScheduler._instance = None
    yield
    ApprovalTimeoutScheduler.get().cancel_all()


@pytest.fixture
def gateway() -> Iterator[AgentGateway]:
    config = GatewayConfig(max_global=10, max_per_user=3, queue_timeout=2.0, execution_timeout=5.0, execution_hard_ceiling=60.0)
    gw = AgentGateway(config)
    with patch.object(hitl_timeout, "get_agent_gateway", return_value=gw):
        yield gw


@pytest.fixture
def persisted() -> Iterator[list[str]]:
    """Chat persistence calls in order, as ``persist:<content>`` and ``answered:<message id>``."""
    calls: list[str] = []

    async def persist(chat_id: str, content: str, **_kwargs: object) -> None:
        calls.append(f"persist:{content}")

    async def update(message_id: str, _extra_data: dict[str, object]) -> None:
        calls.append(f"answered:{message_id}")

    unanswered = MagicMock(role="assistant", id="assistant-row")
    unanswered.extra_data = {"clarification": {"answered": False}}
    with (
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new=persist),
        patch("app.services.chat.chat_service.ChatService.get_all_messages", new=AsyncMock(return_value=[unanswered])),
        patch("app.services.chat.chat_service.ChatService.update_message_extra_data", new=update),
        patch(
            "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots", new=AsyncMock(return_value=["skills/off"])
        ),
    ):
        yield calls


@pytest.fixture
def answered_cards(persisted: list[str]) -> Iterator[dict[str, dict[str, object]]]:
    """The ``extra_data`` written for each card flipped to answered, by message id (on top of ``persisted``)."""
    stored: dict[str, dict[str, object]] = {}

    async def update(message_id: str, extra_data: dict[str, object]) -> None:
        persisted.append(f"answered:{message_id}")
        stored[message_id] = extra_data

    with patch("app.services.chat.chat_service.ChatService.update_message_extra_data", new=update):
        yield stored


def _params() -> MagicMock:
    params = MagicMock()
    params.chat_id = CHAT_ID
    params.message_id = "msg-1"
    params.model_copy.return_value = params
    return params


def _agent_stream(gateway: AgentGateway, events: list[dict[str, object]], seen: list[dict[str, object]]) -> StreamFactory:
    """An ``ai_agent_service_stream`` stand-in that suspends between events and runs through the real gateway."""

    async def stream(
        params: MagicMock, extra_context: dict[str, object] | None = None, **_kwargs: object
    ) -> AsyncGenerator[dict[str, object], None]:
        seen.append({"query": params.query, "extra_context": extra_context})

        async def raw() -> AsyncGenerator[dict[str, object], None]:
            for event in events:
                await asyncio.sleep(0.005)
                yield event

        async for event in gateway.execute_stream(raw(), agent_type="general", session_id=CHAT_ID, active_message_id="msg-1"):
            yield event

    return stream


async def _settle() -> None:
    """Wait until the armed timer has fired and its resume callback has finished."""
    first = ApprovalTimeoutScheduler.get()._tasks.get(CHAT_ID)
    assert first is not None, "no timer was armed"
    await asyncio.wait_for(first, timeout=5)


def _arm(kind: HitlKind, params: MagicMock, monkeypatch: pytest.MonkeyPatch) -> object:
    """Arm ``kind`` with a short timeout; returns the resume value the timer must carry."""
    if kind == "clarification":
        monkeypatch.setattr(hitl_timeout, "CLARIFICATION_TIMEOUT_SECONDS", FAST)
        schedule_clarification_timeout(CHAT_ID, params)
        return CLARIFICATION_NO_ANSWER_RESUME_VALUE
    schedule_approval_timeout(CHAT_ID, {"seconds": FAST, "behavior": "deny"}, params)
    return {"decision": "reject"}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["clarification", "approval"])
async def test_fired_timer_resumes_the_agent_through_the_gateway(
    kind: HitlKind, gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, object]] = []
    params = _params()
    expected = _arm(kind, params, monkeypatch)

    with (
        patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [MESSAGE_EVENT], seen)),
        patch("app.services.agent.runtime_context.resolve_stream_execution_mode", return_value=ExecutionMode.POOLED),
    ):
        await _settle()

    assert len(seen) == 1, "the timer must reach the agent: a callback cancelled at its first await never does"
    query = seen[0]["query"]
    assert isinstance(query, Command)
    if kind == "approval":
        assert isinstance(query.resume, dict) and query.resume["decision"] == "reject"
    else:
        assert query.resume == expected
    extra_context = seen[0]["extra_context"]
    assert isinstance(extra_context, dict)
    assert extra_context["execution_mode"] == "pooled"
    assert extra_context["disabled_skill_roots"] == ["skills/off"]
    assert persisted[-1] == "persist:continued"
    assert not gateway.is_session_active(CHAT_ID)
    assert ApprovalTimeoutScheduler.get().pending_count == 0


@pytest.mark.asyncio
async def test_stored_card_is_marked_answered_before_the_continuation_is_persisted(
    gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    params = _params()
    _arm("clarification", params, monkeypatch)

    with patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [MESSAGE_EVENT], [])):
        await _settle()

    assert persisted == ["answered:assistant-row", "persist:continued"]


@pytest.mark.asyncio
async def test_a_timed_out_card_records_that_the_timeout_answered_it(
    gateway: AgentGateway,
    answered_cards: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = _params()
    expected_value = _arm("clarification", params, monkeypatch)

    with patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [MESSAGE_EVENT], [])):
        await _settle()

    stored = answered_cards["assistant-row"]
    assert stored["clarification"] == {"answered": True, "answerRecord": {"by": "timeout", "value": expected_value}}


@pytest.mark.asyncio
async def test_approval_timeout_leaves_stored_cards_alone(
    gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm("approval", _params(), monkeypatch)

    with patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [MESSAGE_EVENT], [])):
        await _settle()

    assert persisted == ["persist:continued"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "kind"),
    [
        (CLARIFICATION_EVENT, "clarification"),
        (APPROVAL_EVENT, "approval"),
    ],
)
async def test_the_next_interrupt_gets_its_own_timer(
    event: dict[str, object], kind: HitlKind, gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler = ApprovalTimeoutScheduler.get()
    _arm("approval", _params(), monkeypatch)

    with patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [event], [])):
        await _settle()

    assert scheduler.pending_count == 1, f"the resumed run stopped at a {kind} interrupt; its timer must be armed"
    assert scheduler.resolve_if_first(CHAT_ID) is True, "the new timer keeps its handle and a manual answer still wins"
    assert scheduler.pending_count == 0


@pytest.mark.asyncio
async def test_an_interrupt_without_a_timer_stays_answerable(
    gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler = ApprovalTimeoutScheduler.get()
    _arm("approval", _params(), monkeypatch)

    with patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [UNARMED_EVENT], [])):
        await _settle()

    assert scheduler.pending_count == 0
    assert scheduler.resolve_if_first(CHAT_ID) is True, "a plan confirmation has no timer; its answer must not be refused"


@pytest.mark.asyncio
async def test_a_finished_resume_keeps_the_key_resolved_so_a_stale_click_is_refused(
    gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler = ApprovalTimeoutScheduler.get()
    _arm("approval", _params(), monkeypatch)

    with patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [MESSAGE_EVENT], [])):
        await _settle()

    assert scheduler.resolve_if_first(CHAT_ID) is False


@pytest.mark.asyncio
async def test_the_resume_yields_to_a_run_that_is_already_live(
    gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler = ApprovalTimeoutScheduler.get()
    seen: list[dict[str, object]] = []
    gateway.reserve_session(CHAT_ID, active_message_id="user-turn")
    _arm("clarification", _params(), monkeypatch)

    with patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [MESSAGE_EVENT], seen)):
        await _settle()

    assert seen == [], "the live turn owns the suspended graph"
    assert gateway.is_session_active(CHAT_ID), "the live turn's reservation must survive"
    assert scheduler.resolve_if_first(CHAT_ID) is True, "the claim is returned so the card stays answerable"


@pytest.mark.asyncio
async def test_a_failed_resume_releases_the_chat_and_reopens_the_interrupt(
    gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler = ApprovalTimeoutScheduler.get()

    async def failing_stream(*_args: object, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        raise RuntimeError("agent could not be created")
        yield {}  # pragma: no cover

    _arm("clarification", _params(), monkeypatch)

    with patch("app.services.agent.streaming.ai_agent_service_stream", failing_stream):
        await _settle()

    assert not gateway.is_session_active(CHAT_ID), "a reservation that never reached the stream must not leave the chat busy"
    assert scheduler.resolve_if_first(CHAT_ID) is True
    assert persisted == []


@pytest.mark.asyncio
async def test_bookkeeping_failure_still_arms_the_next_interrupt(
    gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler = ApprovalTimeoutScheduler.get()
    _arm("clarification", _params(), monkeypatch)

    with (
        patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [CLARIFICATION_EVENT], [])),
        patch("app.services.chat.chat_service.ChatService.get_all_messages", new=AsyncMock(side_effect=RuntimeError("db down"))),
    ):
        await _settle()

    assert scheduler.pending_count == 1


@pytest.mark.asyncio
async def test_a_card_that_cannot_be_marked_does_not_lose_the_continuation(
    gateway: AgentGateway, persisted: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm("clarification", _params(), monkeypatch)

    with (
        patch("app.services.agent.streaming.ai_agent_service_stream", _agent_stream(gateway, [MESSAGE_EVENT], [])),
        patch("app.services.chat.chat_service.ChatService.get_all_messages", new=AsyncMock(side_effect=RuntimeError("db down"))),
    ):
        await _settle()

    assert persisted == ["persist:continued"]


@pytest.mark.parametrize(
    ("schedule", "seconds", "behavior", "override"),
    [
        (lambda params: schedule_clarification_timeout(CHAT_ID, params), CLARIFICATION_TIMEOUT_SECONDS, "deny", {}),
        (
            lambda params: schedule_approval_timeout(CHAT_ID, {"seconds": "45", "behavior": "allow"}, params),
            45.0,
            "allow",
            None,
        ),
    ],
)
def test_each_kind_registers_its_timeout_decision(
    schedule: Callable[[MagicMock], None], seconds: float, behavior: str, override: dict[str, object] | None
) -> None:
    scheduler = MagicMock()
    with patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler):
        schedule(_params())

    kwargs = scheduler.schedule.call_args.kwargs
    assert kwargs["key"] == CHAT_ID
    assert kwargs["timeout_seconds"] == seconds
    assert kwargs["behavior"] == behavior
    assert kwargs["resume_value_override"] == override
    assert callable(kwargs["resume_callback"])


def test_constants_match_the_documented_timeouts() -> None:
    assert CLARIFICATION_TIMEOUT_SECONDS == 900.0
    assert CLARIFICATION_NO_ANSWER_RESUME_VALUE == {}


@pytest.mark.parametrize("seconds", [object(), None, "soon", float("inf")])
def test_unusable_approval_seconds_fall_back_to_the_default(seconds: object) -> None:
    scheduler = MagicMock()
    with patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler):
        schedule_approval_timeout(CHAT_ID, {"seconds": seconds, "behavior": "deny"}, _params())

    assert scheduler.schedule.call_args.kwargs["timeout_seconds"] == 300.0


@pytest.mark.parametrize(
    ("approval_timeout", "clarification_pending", "armed"),
    [
        ({"seconds": 1}, True, "clarification"),
        ({"seconds": 5, "behavior": "deny"}, False, "approval"),
    ],
)
def test_arm_interrupt_timeout_picks_the_interrupt_that_carries_a_timer(
    approval_timeout: dict[str, object] | None,
    clarification_pending: bool,
    armed: str,
) -> None:
    scheduler = MagicMock()
    with (
        patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler),
        patch.object(hitl_timeout, "schedule_clarification_timeout") as clarification,
        patch.object(hitl_timeout, "schedule_approval_timeout") as approval,
    ):
        arm_interrupt_timeout(
            CHAT_ID,
            _params(),
            approval_timeout=approval_timeout,
            clarification_pending=clarification_pending,
            awaiting_answer=True,
        )

    called = {name for name, mock in (("clarification", clarification), ("approval", approval)) if mock.called}
    assert called == {armed}
    scheduler.reopen.assert_not_called()


@pytest.mark.parametrize(("awaiting_answer", "reopened"), [(True, True), (False, False)])
def test_arm_interrupt_timeout_reopens_only_an_interrupt_without_a_timer(awaiting_answer: bool, reopened: bool) -> None:
    scheduler = MagicMock()
    with patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler):
        arm_interrupt_timeout(
            CHAT_ID,
            _params(),
            approval_timeout=None,
            clarification_pending=False,
            awaiting_answer=awaiting_answer,
        )

    assert scheduler.reopen.called is reopened
