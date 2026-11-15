"""Every way past a pending question reaches the agent: an answer, a skip and the expired timer.

Real app, real agent, real persistence. Only the model is scripted (a localhost OpenAI-compatible endpoint), so what the
agent does after a question is the harness's own behaviour. The live-model e2e needs a key and once passed a skip that
reached nobody; these tests need none and judge by continuation evidence: the agent wrote more after the answer and did
not ask the same question again.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.services.agent.streaming_support import hitl_timeout
from tests.api.agent.scripted_model import (
    TurnResult,
    connection_per_session,
    scripted_model_environment,
    stream_agent_turn,
    wait_for,
)
from tests.support.scripted_openai_endpoint import ChatRequest, Reply, ScriptedOpenAIEndpoint

ASK = "ask_question_tool"
AGENT_CONFIG: dict[str, object] = {"enabledBuiltinTools": ["structured_clarify"]}
FORM: dict[str, object] = {
    "title": "Pick stack",
    "questions": [
        {"id": "stack", "prompt": "Which stack?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
    ],
}
# What a skip or an expired timer tells the agent: it may go on, but the silence is no go-ahead.
SILENCE = (
    "User did not answer the clarification (skipped or timed out). Proceed with your best judgment, but silence is not approval"
)
ASK_AGAIN = "and ask again after silence"
NEVER_MIND = "never mind"
TIMER_SECONDS = 0.4
QUIET_SECONDS = 3.0


def _answers_since_the_last_user_message(request: ChatRequest) -> list[str]:
    answers: list[str] = []
    for message in request.messages:
        if message.get("role") == "user":
            answers = []
        elif message.get("role") == "tool":
            answers.append(str(message.get("content")))
    return answers


def _script(request: ChatRequest) -> Reply:
    """Asks the question, and answers with whatever the question returned (once more after a silence on request)."""
    if ASK not in request.tool_names:
        return Reply(text="ok")
    if NEVER_MIND in request.last_user_text:
        return Reply(text="Fine.")
    answers = _answers_since_the_last_user_message(request)
    asks_again = ASK_AGAIN in request.last_user_text and len(answers) == 1 and answers[0].startswith(SILENCE)
    if not answers or asks_again:
        return Reply(tool_name=ASK, tool_args=FORM)
    return Reply(text=f"CONTINUED: {answers[-1]}")


@pytest.fixture
async def setup_test_database(setup_test_database: None) -> AsyncIterator[None]:
    """A timer resumes the agent while the turn that armed it is still closing; both write, as they would in production."""
    async with connection_per_session(Path(os.environ["TEST_AGENT_DB_PATH"])):
        yield


@pytest.fixture
def scripted_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mock_load_user_configs: AsyncMock
) -> Iterator[ScriptedOpenAIEndpoint]:
    endpoint = ScriptedOpenAIEndpoint(_script)
    with scripted_model_environment(endpoint, monkeypatch, tmp_path, mock_load_user_configs):
        yield endpoint
    endpoint.close()


@pytest.fixture
def short_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hitl_timeout, "CLARIFICATION_TIMEOUT_SECONDS", TIMER_SECONDS)


def _new_chat_id() -> str:
    return f"clarify-{uuid.uuid4().hex[:8]}"


def _ask(client: TestClient, chat_id: str, query: str) -> str:
    """Run a turn that stops at a question; returns the id of the pause its card was announced for."""
    turn = stream_agent_turn(client, chat_id, query=query, agent_config=AGENT_CONFIG)
    cards = turn.of_type("clarification_required")
    assert turn.status == 200
    assert len(cards) == 1
    interrupt_id = cards[0].get("interruptId")
    assert isinstance(interrupt_id, str)
    assert interrupt_id
    return interrupt_id


def _answer(client: TestClient, chat_id: str, interrupt_id: str, answer: dict[str, object]) -> TurnResult:
    """What the page sends: the answer addressed to the pause it is for."""
    return stream_agent_turn(client, chat_id, resume_value={**answer, "interruptId": interrupt_id}, agent_config=AGENT_CONFIG)


def _cards(client: TestClient, chat_id: str) -> list[dict[str, object]]:
    """The clarification cards the chat stores, oldest first."""
    messages = client.get(f"/api/v1/chats/{chat_id}/messages").json()["data"]["messages"]
    return [m["metadata"]["clarification"] for m in messages if m["role"] == "assistant" and "clarification" in m["metadata"]]


def _agent_calls(model: ScriptedOpenAIEndpoint) -> int:
    """How often the agent itself asked the model (side requests such as titles do not offer the question tool)."""
    return len([request for request in model.requests if ASK in request.tool_names])


def _continued(turn: TurnResult) -> bool:
    """Continuation evidence: the agent wrote something after the answer and did not ask the question again."""
    return turn.status == 200 and bool(turn.text) and not turn.of_type("clarification_required")


def _holds_for[T](seconds: float, read: Callable[[], T], expected: T) -> bool:
    """Whether ``read`` keeps returning ``expected`` for the whole of ``seconds``."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if read() != expected:
            return False
        time.sleep(0.1)
    return True


@pytest.mark.integration
@pytest.mark.parametrize(
    ("answer", "tool_result"),
    [({}, SILENCE), ({"stack": "a"}, '{"stack": "a"}')],
    ids=["skip", "answer"],
)
def test_an_answer_addressed_to_its_card_reaches_the_agent_once(
    client: TestClient, scripted_model: ScriptedOpenAIEndpoint, answer: dict[str, object], tool_result: str
) -> None:
    chat_id = _new_chat_id()
    interrupt_id = _ask(client, chat_id, "ask me which stack")
    [card] = _cards(client, chat_id)
    assert card["interruptId"] == interrupt_id, "a reloaded page must be able to address the card"
    assert card["answered"] is False

    turn = _answer(client, chat_id, interrupt_id, answer)

    assert _continued(turn)
    assert turn.text.startswith(f"CONTINUED: {tool_result}")
    [settled] = _cards(client, chat_id)
    assert settled["answered"] is True
    assert settled["answerRecord"] == {"by": "user", "value": answer}, "the record keeps the answer, not its address"

    calls = _agent_calls(scripted_model)
    assert _answer(client, chat_id, interrupt_id, answer).status == 409
    assert _agent_calls(scripted_model) == calls, "a refused answer must not run the agent"


@pytest.mark.integration
def test_a_skip_that_names_no_pause_reaches_nobody(client: TestClient, scripted_model: ScriptedOpenAIEndpoint) -> None:
    """The dead skip: it ends in a bare ``message_end``, which is what the old pass formula accepted."""
    chat_id = _new_chat_id()
    _ask(client, chat_id, "ask me which stack")

    dead = stream_agent_turn(client, chat_id, resume_value={}, agent_config=AGENT_CONFIG)

    assert dead.of_type("message_end"), "this is the turn the old formula passed"
    assert not _continued(dead)
    assert dead.text == ""
    assert len(dead.of_type("clarification_required")) == 1, "the same question is announced again"


@pytest.mark.integration
@pytest.mark.usefixtures("short_timer")
def test_an_expired_timer_skips_one_question_and_the_next_waits_for_the_user(
    client: TestClient, scripted_model: ScriptedOpenAIEndpoint
) -> None:
    chat_id = _new_chat_id()
    first = _ask(client, chat_id, f"ask me which stack, {ASK_AGAIN}")

    cards = wait_for(lambda: _cards(client, chat_id), lambda found: len(found) == 2)
    assert len(cards) == 2, "the timer must resume the agent, which then asks again"
    skipped, asked_again = cards
    assert skipped["interruptId"] == first
    assert skipped["answerRecord"] == {"by": "timeout", "value": {}}
    assert asked_again["answered"] is False
    assert asked_again["interruptId"] not in (None, first)

    quiet = _holds_for(QUIET_SECONDS, lambda: _agent_calls(scripted_model), 2)
    assert quiet, "a timer that chains into the next question would resume the agent again"
    assert _cards(client, chat_id)[-1]["answered"] is False

    interrupt_id = asked_again["interruptId"]
    assert isinstance(interrupt_id, str)
    answered = _answer(client, chat_id, interrupt_id, {"stack": "b"})
    assert _continued(answered)
    assert answered.text == 'CONTINUED: {"stack": "b"}'


@pytest.mark.integration
def test_a_message_sent_instead_of_an_answer_retires_the_pending_card(
    client: TestClient, scripted_model: ScriptedOpenAIEndpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = _new_chat_id()
    # The first question keeps its real timer, which cannot fire during the test: only the message can explain the
    # refusal below. A short timer would race the message, and an answer refused because the timer already ran would
    # pass without the card being retired.
    retired = _ask(client, chat_id, "ask me which stack")

    detour = stream_agent_turn(client, chat_id, query=f"{NEVER_MIND}, forget the question", agent_config=AGENT_CONFIG)
    assert detour.status == 200
    assert detour.text == "Fine."
    calls = _agent_calls(scripted_model)

    assert _answer(client, chat_id, retired, {"stack": "a"}).status == 409, "a late answer must not run a replaced graph"
    assert _agent_calls(scripted_model) == calls

    monkeypatch.setattr(hitl_timeout, "CLARIFICATION_TIMEOUT_SECONDS", TIMER_SECONDS)

    fresh = _ask(client, chat_id, "ask me which stack, once more")
    assert fresh != retired
    settled = wait_for(lambda: _cards(client, chat_id)[-1], lambda card: card["answered"] is True)
    assert settled["answerRecord"] == {"by": "timeout", "value": {}}, "a question asked after the detour still gets its timer"
