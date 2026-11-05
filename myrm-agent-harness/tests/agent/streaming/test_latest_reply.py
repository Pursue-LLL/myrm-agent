"""latest_model_reply: the assistant reply an ``updates`` chunk delivers, including one that is empty."""

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from myrm_agent_harness.agent.streaming.latest_reply import latest_model_reply


def test_returns_an_empty_reply_that_collected_messages_would_drop():
    empty = AIMessage(content="")

    assert latest_model_reply({"model": {"messages": [empty]}}) is empty


def test_returns_the_last_reply_when_a_chunk_carries_several():
    first, last = AIMessage(content="first"), AIMessage(content="last")

    update = {"model": {"messages": [first]}, "after_model": {"messages": [HumanMessage(content="note"), last]}}

    assert latest_model_reply(update) is last


def test_chunk_without_a_reply_returns_none():
    update = {
        "tools": {"messages": [ToolMessage(content="ok", tool_call_id="call_1")]},
        "guard": {"messages": [RemoveMessage(id="gone")]},
    }

    assert latest_model_reply(update) is None


def test_tolerates_chunks_that_are_not_message_updates():
    update = {
        "__interrupt__": ("pause",),
        "state_only": {"counter": 1},
        "bad_messages": {"messages": "not a list"},
        "no_output": None,
    }

    assert latest_model_reply(update) is None
