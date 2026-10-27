"""Which tool calls of a model response already have an answer, and which of them stay in it."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage

from myrm_agent_harness.agent.middlewares.approval.refusal import answered_call_ids, kept_tool_calls


def _call(call_id: str, **args: str) -> ToolCall:
    return ToolCall(type="tool_call", name="step", args=args, id=call_id)


def test_only_the_tool_messages_after_the_ai_message_count_as_answers() -> None:
    older = ToolMessage(content="old", tool_call_id="c0")
    ai = AIMessage(content="", tool_calls=[_call("c1"), _call("c2")], id="ai-1")
    answer = ToolMessage(content="blocked", tool_call_id="c2")

    assert answered_call_ids([HumanMessage(content="hi"), older, ai, answer], ai) == {"c2"}


def test_the_ai_message_is_found_by_id_when_a_hook_handed_back_a_copy() -> None:
    ai = AIMessage(content="", tool_calls=[_call("c1")], id="ai-1")
    stored = ai.model_copy()

    assert answered_call_ids([stored, ToolMessage(content="x", tool_call_id="c1")], ai) == {"c1"}


def test_nothing_is_answered_before_a_guard_has_spoken() -> None:
    ai = AIMessage(content="", tool_calls=[_call("c1")], id="ai-1")

    assert answered_call_ids([ai], ai) == set()


def test_an_approved_call_keeps_its_edit_and_a_refused_call_stays_to_be_answered() -> None:
    original = [_call("c1", text="a"), _call("c2", text="b"), _call("c3", text="c")]
    edited = _call("c1", text="edited")

    kept = kept_tool_calls(original, [edited], {"c2", "c3"})

    assert kept == [edited, original[1], original[2]]


def test_a_call_that_is_neither_approved_nor_answered_is_dropped() -> None:
    original = [_call("c1"), _call("c2")]

    assert kept_tool_calls(original, [original[0]], set()) == [original[0]]


def test_the_order_of_the_model_is_kept() -> None:
    original = [_call("c1"), _call("c2"), _call("c3")]

    assert kept_tool_calls(original, [original[2], original[0]], {"c2"}) == original
