"""Resume addressing against the production graph builder (langchain ``create_agent``).

The model message below issues two tool calls; ``create_agent`` runs each as its own task, so both pause on their own
interrupt at the same time, exactly like two parallel delegations that each ask for approval.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from myrm_agent_harness.agent._internals.resume_addressing import address_resume, address_resume_to_pending
from myrm_agent_harness.agent.streaming.interrupt_events import INTERRUPT_ID_KEY

_PENDING_ID = "a" * 32
_OTHER_PENDING_ID = "b" * 32
# The id the rule rewrites an answer to when it names no pending pause: well-formed, held by nobody.
_NO_INTERRUPT_ID = "0" * 32

_THREAD = "chat"
_CONFIG = {"configurable": {"thread_id": _THREAD}}


class _ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self


@tool
async def ask(topic: str) -> str:
    """Pause until the user answers."""
    answer = interrupt({"topic": topic})
    return f"{topic}:{answer['answer']}"


def _agent() -> object:
    calls = [{"name": "ask", "args": {"topic": topic}, "id": f"call-{topic}"} for topic in ("alpha", "beta")]
    model = _ScriptedModel(responses=[AIMessage(content="", tool_calls=calls), AIMessage(content="all done")])
    return create_agent(model=model, tools=[ask], checkpointer=InMemorySaver())


async def _start() -> object:
    agent = _agent()
    await agent.ainvoke({"messages": [("user", "go")]}, _CONFIG)  # type: ignore[attr-defined]
    return agent


async def _pending(agent: object) -> dict[str, str]:
    """Pending interrupt ids by the topic each one asks about."""
    snapshot = await agent.aget_state(_CONFIG)  # type: ignore[attr-defined]
    return {interrupt_.value["topic"]: interrupt_.id for interrupt_ in snapshot.interrupts}


async def _answer(agent: object, command: Command[object]) -> dict[str, object]:
    addressed = await address_resume_to_pending(agent, command, _THREAD)
    return await agent.ainvoke(addressed, _CONFIG)  # type: ignore[attr-defined,no-any-return]


def _addressed(interrupt_id: str, answer: str) -> Command[object]:
    """An answer carrying the card id of the pause ``interrupt_id``."""
    return Command(resume={"answer": answer, INTERRUPT_ID_KEY: interrupt_id})


def _tool_outputs(state: dict[str, object]) -> dict[str, str]:
    messages: Sequence[object] = state["messages"]  # type: ignore[assignment]
    return {m.tool_call_id: m.content for m in messages if getattr(m, "type", "") == "tool"}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_each_pending_interrupt_is_answered_by_the_id_its_card_carried() -> None:
    agent = await _start()
    ids = await _pending(agent)
    assert set(ids) == {"alpha", "beta"}

    await _answer(agent, _addressed(ids["beta"], "yes-b"))

    assert set(await _pending(agent)) == {"alpha"}
    done = await _answer(agent, _addressed(ids["alpha"], "yes-a"))
    assert _tool_outputs(done) == {"call-alpha": "alpha:yes-a", "call-beta": "beta:yes-b"}


@pytest.mark.asyncio
async def test_an_answer_for_a_settled_interrupt_changes_nothing() -> None:
    agent = await _start()
    ids = await _pending(agent)
    await _answer(agent, _addressed(ids["alpha"], "yes-a"))

    await _answer(agent, _addressed(ids["alpha"], "late repeat"))

    assert await _pending(agent) == {"beta": ids["beta"]}
    done = await _answer(agent, _addressed(ids["beta"], "yes-b"))
    assert _tool_outputs(done) == {"call-alpha": "alpha:yes-a", "call-beta": "beta:yes-b"}


@pytest.mark.asyncio
async def test_a_global_rejection_settles_every_pending_interrupt() -> None:
    agent = await _start()

    rejection = Command[object](resume={"decision": "reject", "feedback": "timed out"})
    addressed = await address_resume_to_pending(agent, rejection, _THREAD)

    assert isinstance(addressed.resume, dict)
    assert set(addressed.resume) == set((await _pending(agent)).values())


@pytest.mark.asyncio
async def test_an_unaddressed_approval_is_still_refused_while_several_interrupts_are_pending() -> None:
    agent = await _start()
    approval = Command[object](resume={"answer": "yes"})

    assert (await address_resume_to_pending(agent, approval, _THREAD)).resume == approval.resume
    with pytest.raises(RuntimeError, match="multiple pending interrupts"):
        await agent.ainvoke(approval, _CONFIG)  # type: ignore[attr-defined]
    assert set(await _pending(agent)) == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_an_unaddressed_answer_is_untouched_while_one_interrupt_is_pending() -> None:
    agent = await _start()
    ids = await _pending(agent)
    await _answer(agent, _addressed(ids["alpha"], "yes-a"))
    plain = Command[object](resume={"answer": "yes-b"})

    rejection = Command[object](resume={"decision": "reject", "feedback": "timed out"})

    assert (await address_resume_to_pending(agent, plain, _THREAD)).resume == plain.resume
    assert (await address_resume_to_pending(agent, rejection, _THREAD)).resume == rejection.resume
    done = await agent.ainvoke(plain, _CONFIG)  # type: ignore[attr-defined]
    assert _tool_outputs(done)["call-beta"] == "beta:yes-b"


@pytest.mark.asyncio
async def test_an_addressed_answer_on_a_finished_thread_changes_nothing() -> None:
    agent = await _start()
    ids = await _pending(agent)
    await _answer(agent, _addressed(ids["alpha"], "yes-a"))
    finished = await _answer(agent, _addressed(ids["beta"], "yes-b"))

    again = await _answer(agent, _addressed(ids["beta"], "late repeat"))

    assert _tool_outputs(again) == _tool_outputs(finished)


def test_the_card_id_is_removed_from_the_answer_the_interrupt_receives() -> None:
    addressed = address_resume(_addressed(_PENDING_ID, "yes"), {_PENDING_ID})

    assert addressed.resume == {_PENDING_ID: {"answer": "yes"}}


def test_a_command_keeps_its_other_fields_when_addressed() -> None:
    command = Command[object](resume={"answer": "yes", INTERRUPT_ID_KEY: _PENDING_ID}, update={"messages": []})

    assert address_resume(command, {_PENDING_ID}).update == {"messages": []}


def test_an_answer_naming_a_pause_that_is_not_pending_is_rewritten_to_an_id_nobody_holds() -> None:
    addressed = address_resume(_addressed("c" * 32, "yes"), {_PENDING_ID, _OTHER_PENDING_ID})

    assert addressed.resume == {_NO_INTERRUPT_ID: {"answer": "yes"}}


def test_a_global_rejection_is_broadcast_only_while_several_interrupts_are_pending() -> None:
    rejection = Command[object](resume={"decision": "reject", "feedback": "timed out"})

    several = address_resume(rejection, {_PENDING_ID, _OTHER_PENDING_ID})
    one = address_resume(rejection, {_PENDING_ID})

    assert several.resume == {_PENDING_ID: rejection.resume, _OTHER_PENDING_ID: rejection.resume}
    assert one.resume == rejection.resume


def test_an_unaddressed_approval_is_never_broadcast() -> None:
    approval = Command[object](resume={"decisions": [{"type": "approve"}]})

    assert address_resume(approval, {_PENDING_ID, _OTHER_PENDING_ID}).resume == approval.resume


def test_the_log_of_an_ignored_answer_stays_short_however_long_the_client_id_is(
    caplog: pytest.LogCaptureFixture,
) -> None:
    hostile = Command[object](resume={"answer": "yes", INTERRUPT_ID_KEY: "x" * 100_000})

    with caplog.at_level("WARNING"):
        address_resume(hostile, {_PENDING_ID})

    [record] = caplog.records
    assert "xxxx" in record.getMessage()
    assert len(record.getMessage()) < 300


@pytest.mark.asyncio
async def test_a_thread_that_cannot_be_read_leaves_the_command_untouched() -> None:
    class _Broken:
        async def aget_state(self, config: object) -> object:
            raise OSError("checkpoint store unavailable")

    command = _addressed("abc", "yes")

    assert await address_resume_to_pending(_Broken(), command, _THREAD) is command
    assert await address_resume_to_pending(None, command, _THREAD) is command
