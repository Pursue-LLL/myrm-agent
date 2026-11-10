"""The circuit-breaker constraints are written once per distinct list and stay behind the message they followed."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.middlewares._session_context import get_terminal_errors, reset_terminal_errors
from myrm_agent_harness.agent.middlewares.security.security_guardrail_middleware import SecurityGuardrailMiddleware
from myrm_agent_harness.core.message_origin import is_user_authored_human_message

_CONSTRAINTS = "[SYSTEM_ENFORCED] Environment capability constraints detected:"


@pytest.fixture(autouse=True)
def _clean_terminal_errors() -> Iterator[None]:
    reset_terminal_errors()
    yield
    reset_terminal_errors()


def _history(rounds: int) -> list[AnyMessage]:
    messages: list[AnyMessage] = [HumanMessage(content="search it", id="u1")]
    for n in range(rounds):
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[{"id": f"c{n}", "name": "t", "args": {}}]))
        messages.append(ToolMessage(content=f"result {n}", id=f"t{n}", tool_call_id=f"c{n}"))
    return messages


async def _sent(messages: list[AnyMessage], context: dict[str, object] | None) -> list[AnyMessage]:
    handler = AsyncMock(return_value=ModelResponse(result=[]))
    runtime = None if context is None else Runtime(context=context)
    await SecurityGuardrailMiddleware().awrap_model_call(
        ModelRequest(model=AsyncMock(), messages=messages, runtime=runtime), handler
    )
    return handler.await_args_list[-1].args[0].messages


def _notice_positions(messages: list[AnyMessage]) -> list[int]:
    return [i for i, m in enumerate(messages) if str(m.content).startswith(_CONSTRAINTS)]


@pytest.mark.asyncio
async def test_a_run_without_terminal_errors_is_sent_as_it_is() -> None:
    messages = _history(1)

    assert await _sent(messages, {}) == messages


@pytest.mark.asyncio
async def test_the_notice_stays_behind_the_message_that_was_last_when_it_was_written() -> None:
    context: dict[str, object] = {}
    await _sent(_history(1), context)
    get_terminal_errors().add("network_blocked")

    first = await _sent(_history(1), context)
    later = await _sent(_history(3), context)

    assert _notice_positions(first) == [3]
    assert _notice_positions(later) == [3], "later results go behind the notice, the notice does not move to them"


@pytest.mark.asyncio
async def test_every_request_of_the_run_extends_the_one_before() -> None:
    context: dict[str, object] = {}
    get_terminal_errors().add("network_blocked")
    views = []
    for rounds in (1, 2, 3):
        views.append(await _sent(_history(rounds), context))
        if rounds == 2:
            get_terminal_errors().add("sandbox_ro")

    for earlier, later in itertools.pairwise(views):
        assert later[: len(earlier)] == earlier


@pytest.mark.asyncio
async def test_a_changed_constraint_list_is_a_new_notice_and_the_first_one_stays() -> None:
    context: dict[str, object] = {}
    get_terminal_errors().add("network_blocked")
    await _sent(_history(1), context)
    get_terminal_errors().add("sandbox_ro")

    sent = await _sent(_history(2), context)

    first, second = (sent[i] for i in _notice_positions(sent))
    assert "READ-ONLY" not in str(first.content)
    assert "READ-ONLY" in str(second.content)
    assert _notice_positions(sent) == [3, 6]


@pytest.mark.asyncio
async def test_an_unchanged_constraint_list_is_not_written_again() -> None:
    context: dict[str, object] = {}
    get_terminal_errors().add("network_blocked")

    for rounds in (1, 2, 3):
        sent = await _sent(_history(rounds), context)

    assert len(_notice_positions(sent)) == 1


@pytest.mark.asyncio
async def test_a_global_network_block_supersedes_the_family_guidance() -> None:
    get_terminal_errors().add("network_blocked")
    get_terminal_errors().add("config_or_auth:search")

    sent = await _sent(_history(1), {})

    (notice,) = (sent[i] for i in _notice_positions(sent))
    assert "Network access is BLOCKED" in str(notice.content)
    assert "Search tools are currently unavailable" not in str(notice.content)


@pytest.mark.asyncio
async def test_the_notice_is_written_by_the_runtime_not_the_user() -> None:
    get_terminal_errors().add("network_blocked")

    sent = await _sent(_history(1), {})

    (position,) = _notice_positions(sent)
    assert not is_user_authored_human_message(sent[position])


@pytest.mark.asyncio
async def test_a_request_without_a_run_scope_gets_the_notice_at_the_end_every_time() -> None:
    get_terminal_errors().add("network_blocked")

    first = await _sent(_history(1), None)
    later = await _sent(_history(2), None)

    assert _notice_positions(first) == [len(first) - 1]
    assert _notice_positions(later) == [len(later) - 1]


@pytest.mark.asyncio
async def test_the_messages_the_middleware_was_given_are_left_alone() -> None:
    get_terminal_errors().add("network_blocked")
    messages = _history(1)

    await _sent(messages, {})

    assert len(messages) == 3
