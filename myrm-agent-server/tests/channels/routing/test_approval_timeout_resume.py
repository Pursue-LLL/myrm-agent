"""An approval nobody answers in time is resolved by the router, and the run resumes as an ordinary router turn.

Runs on the real ``AgentRouter`` and the real ``ApprovalTimeoutScheduler``. The end-to-end cases go through the real
``SessionGate``, so the resumed run is registered like any other turn: ``/stop`` reaches it, which a resume made
behind the router's back could not guarantee.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncGenerator, Iterator
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.i18n import get_text
from app.channels.routing.pending_approvals import METADATA_APPROVAL_TIMED_OUT_KEY
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import ApprovalExpiry, InboundMessage, ProgressUpdate, QuickReply, StreamingText
from tests.support.pending_approvals import asked_in

_CHAT_KEY = "telegram:c1"
_TIMER_SECONDS = 0.05
Behavior = Literal["allow", "deny"]


@pytest.fixture(autouse=True)
def _scheduler() -> Iterator[ApprovalTimeoutScheduler]:
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.cancel_all()
    yield scheduler
    scheduler.cancel_all()


def _inbound(content: str = "build it", *, locale: str = "en", group: bool = False) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="c1",
        content=content,
        user_id="u1",
        is_group=group,
        message_id="m1",
        metadata={"locale": locale},
    )


class _Run:
    """The agent: the first call stops at a tool approval, the resumed call hangs until a stop cancels it."""

    def __init__(self, behavior: Behavior = "deny") -> None:
        self._behavior = behavior
        self.calls: list[InboundMessage] = []
        self.resumed = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def execute_stream(self, msg: InboundMessage, user_id: str, **_: object) -> AsyncGenerator[object, None]:
        self.calls.append(msg)
        if msg.resume_value is None:
            yield StreamingText(text="checking the build")
            yield ProgressUpdate(
                label="shell needs approval: run the build",
                quick_replies=(QuickReply(label="Approve", text="/approve", required=True),),
                expiry=ApprovalExpiry(seconds=_TIMER_SECONDS, behavior=self._behavior),
            )
            return
        yield StreamingText(text="resuming")
        self.resumed.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


def _router(run: _Run | None = None, *, record_resumes: bool = False) -> tuple[AgentRouter, MagicMock]:
    """A real router; with ``record_resumes`` its gate only records the messages it is asked to run."""
    bus = MagicMock()
    bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
    bus.publish_outbound = AsyncMock()
    bus.edit_channel_message = AsyncMock(return_value=True)
    bus.send_tracked = AsyncMock(return_value="prompt-1")
    bus.get_channel = MagicMock(return_value=None)
    executor = MagicMock()
    executor.execute_stream = run.execute_stream if run is not None else None
    router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=executor)
    router._resolve_mobile_status_deep_link = AsyncMock(return_value=None)  # type: ignore[method-assign]
    router._resolve_topic = AsyncMock(return_value=None)  # type: ignore[method-assign]
    if record_resumes:
        router._gate.submit = MagicMock()  # type: ignore[method-assign]
    return router, bus


def _said(bus: MagicMock) -> list[str]:
    return [call.args[0].content for call in bus.publish_outbound.call_args_list]


async def _until(condition: asyncio.Event) -> None:
    await asyncio.wait_for(condition.wait(), timeout=5)


def _wait_on_approval(router: AgentRouter, *, card_message_id: str = "card-1", locale: str = "en") -> None:
    asked = asked_in(card_message_id=card_message_id, locale=locale)
    router._pending_approvals.register(_CHAT_KEY, asked, ApprovalExpiry(seconds=_TIMER_SECONDS))


def _entry(task: asyncio.Task[object]) -> _ActiveTask:
    return _ActiveTask(
        task=task,  # type: ignore[arg-type]
        cancel_token=CancellationToken(),
        channel="telegram",
        chat_id="c1",
        placeholder_id=None,
        started_at=0.0,
        requester_id="u1",
    )


async def _let_the_timer_fire() -> None:
    await asyncio.sleep(_TIMER_SECONDS * 4)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("behavior", "decision", "notice"),
    [("deny", "reject", "approval_timeout_denied"), ("allow", "approve", "approval_timeout_approved")],
)
async def test_an_unanswered_approval_resumes_the_run_as_a_turn_that_stop_can_end(
    behavior: Behavior, decision: str, notice: str
) -> None:
    run = _Run(behavior)
    router, bus = _router(run)
    asking = _inbound()
    router._gate.submit(asking)

    await _until(run.resumed)

    resume = run.calls[1]
    assert resume.resume_value is not None and resume.resume_value["decision"] == decision
    assert resume.content == "" and resume.user_id == "u1"
    assert resume.metadata["is_resume"] is True and resume.metadata[METADATA_APPROVAL_TIMED_OUT_KEY] is True
    bus.edit_channel_message.assert_awaited_once_with("telegram", "c1", "prompt-1", get_text(asking, notice))
    assert _CHAT_KEY not in router._pending_approvals
    assert not router._active_tasks[_CHAT_KEY].task.done()  # the resumed run is a router turn, not a detached one

    await router._cancel_active_task(_inbound("/stop"))

    await _until(run.cancelled)
    assert _CHAT_KEY not in router._active_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "ja", "zh-CN"])
async def test_the_outcome_is_told_in_the_language_the_approval_was_asked_in(locale: str) -> None:
    router, bus = _router(record_resumes=True)
    _wait_on_approval(router, card_message_id="card-1", locale=locale)

    await _let_the_timer_fire()

    expected = get_text(_inbound(locale=locale), "approval_timeout_denied")
    bus.edit_channel_message.assert_awaited_once_with("telegram", "c1", "card-1", expected)
    if locale != "en":
        assert expected != get_text(_inbound(), "approval_timeout_denied")


@pytest.mark.asyncio
@pytest.mark.parametrize("edit_result", [None, False])
async def test_the_outcome_is_sent_as_a_message_when_the_card_cannot_carry_it(edit_result: bool | None) -> None:
    router, bus = _router(record_resumes=True)
    card_message_id = "" if edit_result is None else "card-1"
    bus.edit_channel_message = AsyncMock(return_value=bool(edit_result))
    _wait_on_approval(router, card_message_id=card_message_id)

    await _let_the_timer_fire()

    assert _said(bus) == [get_text(_inbound(), "approval_timeout_denied")]
    assert bus.edit_channel_message.await_count == (0 if edit_result is None else 1)
    router._gate.submit.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_the_resume_message_replaces_the_finished_entry_of_the_turn_that_asked() -> None:
    router, _bus = _router(record_resumes=True)
    finished = asyncio.create_task(asyncio.sleep(0))
    await finished
    router._active_tasks[_CHAT_KEY] = _entry(finished)
    _wait_on_approval(router)

    await _let_the_timer_fire()

    assert _CHAT_KEY not in router._active_tasks
    router._gate.submit.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_an_answer_before_the_timeout_resumes_the_run_once_and_the_timer_never_fires() -> None:
    router, bus = _router(record_resumes=True)
    router._active_tasks[_CHAT_KEY] = _entry(asyncio.create_task(asyncio.Event().wait()))
    _wait_on_approval(router)

    await router._handle_approval_command(_inbound("/approve"), "allow_once")
    await _let_the_timer_fire()

    router._gate.submit.assert_called_once()  # type: ignore[attr-defined]
    resume = router._gate.submit.call_args.args[0]  # type: ignore[attr-defined]
    assert resume.resume_value["decisions"][0]["type"] == "approve"
    assert METADATA_APPROVAL_TIMED_OUT_KEY not in resume.metadata
    router._active_tasks[_CHAT_KEY].task.cancel()


@pytest.mark.asyncio
async def test_an_answer_after_the_timeout_is_told_the_wait_is_over_and_resumes_nothing() -> None:
    router, bus = _router(record_resumes=True)
    router._active_tasks[_CHAT_KEY] = _entry(asyncio.create_task(asyncio.Event().wait()))
    _wait_on_approval(router)
    await _let_the_timer_fire()
    router._gate.submit.assert_called_once()  # type: ignore[attr-defined]  # the timeout's own resume

    await router._handle_approval_command(_inbound("/approve"), "allow_once")

    assert _said(bus)[-1] == get_text(_inbound(), "no_pending_approval")
    router._gate.submit.assert_called_once()  # type: ignore[attr-defined]
    router._active_tasks[_CHAT_KEY].task.cancel()


class TestAdmissionOfTheResume:
    """The sender of a resume was admitted when the run began; nothing new is decided about them."""

    @staticmethod
    def _router_that_admits_nobody() -> tuple[AgentRouter, AsyncMock]:
        """The router and the group admission check it would consult, which turns every sender away."""
        router, _bus = _router(record_resumes=True)
        admit_group_member = AsyncMock(return_value=None)
        router._resolver = MagicMock(resolve_group_user=admit_group_member, resolve_dm_user=AsyncMock(return_value=None))
        return router, admit_group_member

    @pytest.mark.asyncio
    async def test_a_group_run_resumes_without_a_new_admission(self) -> None:
        router, admit_group_member = self._router_that_admits_nobody()
        resume = asked_in(is_group=True, user_id="owner-1").resume_message({"decision": "reject"})

        ctx = await router._prepare_execution_context(resume)

        assert ctx is not None and ctx.user_id == "owner-1"
        admit_group_member.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_marker_without_a_resume_value_is_not_trusted(self) -> None:
        router, admit_group_member = self._router_that_admits_nobody()
        forged = asked_in(is_group=True).message
        forged.metadata[METADATA_APPROVAL_TIMED_OUT_KEY] = True

        assert await router._prepare_execution_context(forged) is None
        admit_group_member.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_resume_without_the_identity_it_ran_as_is_not_trusted(self) -> None:
        router, admit_group_member = self._router_that_admits_nobody()
        resume = asked_in(is_group=True).resume_message({"decision": "reject"})
        anonymous = dataclasses.replace(resume, user_id=None)

        assert await router._prepare_execution_context(anonymous) is None
        admit_group_member.assert_awaited_once()
