"""Messages of named agents reach the model led by ``[Agent: name]``, once, and only where there is text to lead.

The tag is what lets the model tell the agents of a shared thread apart. It is applied to the request on every model
call, so a message that already carries it must come back unchanged: tagging it again would grow the message by one
prefix per call.

[INPUT]
- agent.middlewares.memory_context.memory_context_middleware::_attribute_ai_messages (POS: leads every named AI message of a request with its agent tag)
- agent.middlewares.memory_context.memory_context_middleware::memory_context_middleware (POS: applies the tagging first on every model call, then injects the block)

[POS]
Tagging guard for the memory middleware's agent attribution.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import (
    _attribute_ai_messages,
    memory_context_middleware,
)
from myrm_agent_harness.toolkits.memory.config import RecallMode
from tests.support.memory_context_stubs import bound_manager, make_request


def _request(*messages: AnyMessage) -> MagicMock:
    request = MagicMock()
    request.messages = list(messages)
    request.override = MagicMock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    return request


def _ai_message(request: ModelRequest) -> AIMessage:
    return next(m for m in request.messages if isinstance(m, AIMessage))


def test_a_named_agent_message_with_text_is_led_by_its_tag() -> None:
    request = _request(SystemMessage(content="sys"), AIMessage(content="plan ready", name="planner"))

    assert _ai_message(_attribute_ai_messages(request)).content == "[Agent: planner]\nplan ready"


def test_a_structured_message_has_only_its_first_text_block_led_and_nothing_else_touched() -> None:
    original = AIMessage(
        content=[{"type": "text", "text": "listed"}, {"type": "image", "url": "https://example.com/a.png"}],
        name="researcher",
    )
    untouched = copy.deepcopy(original)

    tagged = _ai_message(_attribute_ai_messages(_request(original)))

    assert tagged.content == [
        {"type": "text", "text": "[Agent: researcher]\nlisted"},
        {"type": "image", "url": "https://example.com/a.png"},
    ]
    assert original == untouched


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("[Agent: planner]\nplan ready", id="text"),
        pytest.param([{"type": "text", "text": "[Agent: planner]\nplan ready"}], id="first-text-block"),
    ],
)
def test_a_message_that_already_carries_its_tag_comes_back_unchanged(content: str | list[str | dict[str, str]]) -> None:
    request = _request(AIMessage(content=content, name="planner"), HumanMessage(content="go"))

    assert _attribute_ai_messages(request) is request
    request.override.assert_not_called()


@pytest.mark.parametrize(
    "content",
    [
        pytest.param([], id="no-content"),
        pytest.param([{"type": "image", "url": "https://example.com/a.png"}], id="image-first"),
        pytest.param([{"type": "text", "text": 7}], id="text-that-is-not-a-string"),
        pytest.param(
            [{"type": "tool_result", "content": "nope"}, {"type": "text", "text": "body"}],
            id="text-only-after-a-non-text-block",
        ),
    ],
)
def test_a_message_without_text_to_lead_is_not_tagged(content: list[str | dict[str, object]]) -> None:
    request = _request(AIMessage(content=content, name="planner"))

    assert _attribute_ai_messages(request) is request
    request.override.assert_not_called()


def test_a_message_without_an_agent_name_is_not_tagged() -> None:
    request = _request(AIMessage(content="plain"), HumanMessage(content="hi"))

    assert _attribute_ai_messages(request) is request


async def test_aimessage_name_prefix():
    """AIMessages with a 'name' attribute get prefixed with [Agent: {Name}]."""
    handler = AsyncMock()
    req = make_request(
        messages=[
            SystemMessage(content="sys"),
            AIMessage(content="I am a response", name="SubAgentA"),
            HumanMessage(content="Hello"),
        ]
    )

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value={})

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    req.override.assert_called_once()
    injected_messages = req.override.call_args[1]["messages"]
    ai_msg = next((m for m in injected_messages if isinstance(m, AIMessage)), None)
    assert ai_msg is not None
    assert ai_msg.content.startswith("[Agent: SubAgentA]\n")
    assert "I am a response" in ai_msg.content


async def test_aimessage_name_prefix_for_list_content_blocks():
    """AIMessages with structured content blocks get the same agent name prefix."""
    handler = AsyncMock()
    req = make_request(
        messages=[
            SystemMessage(content="sys"),
            AIMessage(
                content=[{"type": "text", "text": "Structured response"}],
                name="SubAgentB",
            ),
            HumanMessage(content="Hello"),
        ]
    )

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value={})

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    req.override.assert_called_once()
    injected_messages = req.override.call_args[1]["messages"]
    ai_msg = next((m for m in injected_messages if isinstance(m, AIMessage)), None)
    assert ai_msg is not None
    assert isinstance(ai_msg.content, list)
    assert ai_msg.content[0]["text"].startswith("[Agent: SubAgentB]\n")
