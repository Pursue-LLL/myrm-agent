"""Tests for the wire-encodability scrub: a request body must never carry a code point UTF-8 cannot encode.

[INPUT]
- adapters.chat_model.wire_encoding::replace_lone_surrogates (POS: the scrub under test)
- adapters.chat_model::ChatLiteLLM (POS: owner of the single funnel every model request is built through)
- adapters.chat_model.outbound_guard::set_outbound_message_guard (POS: policy hook that runs after the scrub)
- httpx (POS: the transport whose ``json=`` encoding is where an unencodable string fails)

[OUTPUT]
- Fails when a lone surrogate (what Python gives a file name or output that was not valid UTF-8) survives into the wire
  messages, when a text that was already encodable is copied, or when the outbound guard sees unscrubbed text.

[POS]
One undecodable file name in a tool result or workspace listing would otherwise fail every later model call of the
conversation with an opaque server error, because the history is re-sent each turn. The scrub is the last pure step of
the funnel, so it is exercised both on its own and through ``_create_message_dicts``.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.toolkits.llms.adapters.chat_model import ChatLiteLLM
from myrm_agent_harness.toolkits.llms.adapters.chat_model.outbound_guard import set_outbound_message_guard
from myrm_agent_harness.toolkits.llms.adapters.chat_model.wire_encoding import replace_lone_surrogates

LONE = "\udc80"  # what os.fsdecode gives the byte 0x80 of a name that is not valid UTF-8
REPLACED = "\ufffd"


def _encode_like_the_transport(messages: list[dict[str, object]]) -> None:
    """Build a request the way httpx does for ``json=``; raises UnicodeEncodeError on a lone surrogate."""
    httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions", json={"messages": messages})


@pytest.fixture(autouse=True)
def _no_guard() -> Iterator[None]:
    yield
    set_outbound_message_guard(None)


class TestReplaceLoneSurrogates:
    def test_the_failure_this_prevents_is_real(self) -> None:
        with pytest.raises(UnicodeEncodeError):
            _encode_like_the_transport([{"role": "user", "content": f"ls: {LONE}.txt"}])

    def test_a_string_content_is_scrubbed(self) -> None:
        messages: list[dict[str, object]] = [{"role": "user", "content": f"a{LONE}b"}]

        replace_lone_surrogates(messages)

        assert messages[0]["content"] == f"a{REPLACED}b"
        _encode_like_the_transport(messages)

    def test_a_surrogate_pair_is_two_unencodable_characters(self) -> None:
        messages: list[dict[str, object]] = [{"role": "user", "content": "\ud83d\ude00"}]

        replace_lone_surrogates(messages)

        assert messages[0]["content"] == REPLACED * 2

    def test_content_blocks_tool_calls_and_nested_values_are_scrubbed(self) -> None:
        messages: list[dict[str, object]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"x{LONE}"},
                    {"type": "image_url", "image_url": {"url": f"u{LONE}"}},
                ],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c", "function": {"name": "f", "arguments": f'{{"p": "{LONE}"}}'}}],
            },
            {"role": "tool", "tool_call_id": "c", "name": f"n{LONE}", "content": f"out {LONE}"},
        ]

        replace_lone_surrogates(messages)

        assert messages == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"x{REPLACED}"},
                    {"type": "image_url", "image_url": {"url": f"u{REPLACED}"}},
                ],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c", "function": {"name": "f", "arguments": f'{{"p": "{REPLACED}"}}'}}],
            },
            {"role": "tool", "tool_call_id": "c", "name": f"n{REPLACED}", "content": f"out {REPLACED}"},
        ]
        _encode_like_the_transport(messages)

    @pytest.mark.parametrize(
        "text", ["", "plain ascii", "naïve café", "\u4e2d\u6587", "emoji \U0001f600", "\ufffd", "\x00\x1b control"]
    )
    def test_an_encodable_text_is_the_same_object(self, text: str) -> None:
        content = "".join([text, ""])  # a fresh object, so identity below is not interning luck
        message: dict[str, object] = {"role": "user", "content": content, "blocks": [content]}
        messages = [message]

        replace_lone_surrogates(messages)

        assert message["content"] is content
        assert message["blocks"][0] is content  # type: ignore[index]

    def test_values_that_are_not_text_are_left_alone(self) -> None:
        payload = {
            "role": "assistant",
            "n": 3,
            "flag": True,
            "none": None,
            "ratio": 0.5,
            "raw": b"\xff",
            "tuple": (LONE,),
        }
        messages: list[dict[str, object]] = [dict(payload)]

        replace_lone_surrogates(messages)

        assert messages == [payload]

    def test_an_empty_request_is_a_no_op(self) -> None:
        messages: list[dict[str, object]] = []

        replace_lone_surrogates(messages)

        assert messages == []


class TestThroughTheFunnel:
    @staticmethod
    def _model() -> ChatLiteLLM:
        return ChatLiteLLM.model_construct(client=MagicMock(), model="gpt-5-chat")

    def test_every_message_kind_leaves_the_funnel_encodable(self) -> None:
        history = [
            SystemMessage(content=f"workspace: /work/{LONE}"),
            HumanMessage(content=f"list {LONE}"),
            AIMessage(content="", tool_calls=[{"name": "ls", "args": {"path": "."}, "id": "c1"}]),
            ToolMessage(content=f"a.txt\n{LONE}.txt", tool_call_id="c1"),
        ]

        dicts, _ = self._model()._create_message_dicts(history, None)

        _encode_like_the_transport(dicts)
        assert dicts[0]["content"] == f"workspace: /work/{REPLACED}"
        assert dicts[3]["content"] == f"a.txt\n{REPLACED}.txt"

    def test_an_encodable_history_reaches_the_wire_untouched(self) -> None:
        content = "".join(["héllo ", "wörld"])
        dicts, _ = self._model()._create_message_dicts([HumanMessage(content=content)], None)

        assert dicts[0]["content"] is content

    def test_the_outbound_guard_sees_the_scrubbed_text(self) -> None:
        seen: list[object] = []
        set_outbound_message_guard(lambda messages: seen.extend(m["content"] for m in messages))

        self._model()._create_message_dicts([HumanMessage(content=f"x{LONE}")], None)

        assert seen == [f"x{REPLACED}"]
