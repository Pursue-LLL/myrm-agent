"""Converse messages: what a chat history becomes under the API's turn rules, and how tool names survive its alphabet.

Converse refuses what OpenAI accepts: turns must alternate, a user turn may not mix text with tool results, text may
not be blank. Each rule here is one the API enforces; ``test_every_history_becomes_a_valid_conversation`` walks all
short histories of the message kinds a conversation holds and checks the rules as invariants.
"""

from __future__ import annotations

import itertools
import json
import logging
import re

import pytest

from myrm_agent_harness.toolkits.llms.transport.bedrock_content import (
    Block,
    cache_point,
    decode_tool_name,
    encode_tool_name,
    to_turns,
)

Message = dict[str, object]
CLAUDE = "anthropic.claude-3-5-sonnet-20241022-v2:0"
CLAUDE_4_5 = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
NOVA = "amazon.nova-pro-v1:0"
CONTINUE = [{"text": "Please continue."}]
PNG = "data:image/png;base64,iVBORw0KGgo="


def _call(call_id: object = "call_1", name: str = "get_weather", arguments: object = '{"city": "Paris"}') -> Message:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def _turns(messages: list[Message], model: str = CLAUDE) -> list[tuple[str, list[Block]]]:
    return to_turns(messages, model)[1]


def _text(content: str) -> Block:
    return {"text": content}


class TestToolNames:
    @pytest.mark.parametrize("name", ["get_weather", "a-b", "A1", "x", "search_web-2"])
    def test_a_name_the_api_accepts_is_left_alone(self, name: str) -> None:
        assert encode_tool_name(name) == name

    @pytest.mark.parametrize(
        "name",
        ["web.search", "my tool", "名前", "1abc", "_lead", "a/b:c", "x__prefixed", "x__", "", "emoji🙂tool", "A.B.C"],
    )
    def test_any_other_name_survives_the_round_trip_in_the_api_alphabet(self, name: str) -> None:
        encoded = encode_tool_name(name)
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", encoded)
        assert decode_tool_name(encoded) == name

    def test_a_name_that_looks_escaped_is_escaped_again_not_taken_for_one(self) -> None:
        assert decode_tool_name(encode_tool_name("x__web_2e_search")) == "x__web_2e_search"

    def test_distinct_names_never_share_an_encoding(self) -> None:
        names = ["a.b", "a_b", "a-b", "a b", "x__a_2e_b", "a.b ", "a.B"]
        assert len({encode_tool_name(n) for n in names}) == len(names)

    def test_a_name_the_model_returns_unescaped_is_taken_as_it_is(self) -> None:
        assert decode_tool_name("get_weather") == "get_weather"


class TestRoles:
    def test_system_and_developer_messages_become_system_blocks(self) -> None:
        messages: list[Message] = [
            {"role": "system", "content": "one"},
            {"role": "developer", "content": [{"type": "text", "text": "two"}]},
            {"role": "user", "content": "hi"},
        ]
        system, turns = to_turns(messages, CLAUDE)
        assert system == [_text("one"), _text("two")]
        assert turns == [("user", [_text("hi")])]

    def test_a_blank_system_prompt_is_no_system_prompt(self) -> None:
        assert to_turns([{"role": "system", "content": "  \n"}, {"role": "user", "content": "hi"}], CLAUDE)[0] == []

    def test_neighbours_of_one_role_share_a_turn(self) -> None:
        turns = _turns([{"role": "user", "content": "a"}, {"role": "user", "content": "b"}])
        assert turns == [("user", [_text("a"), _text("b")])]

    def test_a_conversation_that_opens_with_the_assistant_gets_a_user_turn_first(self) -> None:
        turns = _turns([{"role": "assistant", "content": "prefill"}, {"role": "user", "content": "q"}])
        assert turns == [("user", CONTINUE), ("assistant", [_text("prefill")]), ("user", [_text("q")])]

    def test_a_conversation_that_ends_with_the_assistant_gets_a_user_turn_last(self) -> None:
        turns = _turns([{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])
        assert turns[-1] == ("user", CONTINUE)
        assert [role for role, _ in turns] == ["user", "assistant", "user"]

    def test_an_empty_conversation_is_one_user_turn(self) -> None:
        assert _turns([]) == [("user", CONTINUE)]

    def test_blank_messages_vanish_and_their_neighbours_merge(self) -> None:
        turns = _turns(
            [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "   "},
                {"role": "user", "content": ""},
                {"role": "user", "content": None},
                {"role": "user", "content": "b"},
            ]
        )
        assert turns == [("user", [_text("a"), _text("b")])]

    def test_blank_text_parts_vanish_too(self) -> None:
        parts = [
            {"type": "text", "text": " "},
            {"type": "text", "text": "x"},
            {"type": "text", "text": ""},
            {"type": "text"},
        ]
        assert _turns([{"role": "user", "content": parts}]) == [("user", [_text("x")])]

    def test_text_parts_given_as_bare_strings_are_read(self) -> None:
        assert _turns([{"role": "user", "content": ["a", {"type": "text", "text": "b"}]}]) == [
            ("user", [_text("a"), _text("b")])
        ]


class TestToolTurns:
    def test_a_tool_round_trip_pairs_the_call_with_its_result(self) -> None:
        turns = _turns(
            [
                {"role": "user", "content": "weather?"},
                {"role": "assistant", "content": "", "tool_calls": [_call()]},
                {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
            ]
        )
        assert turns[1] == (
            "assistant",
            [{"toolUse": {"toolUseId": "call_1", "name": "get_weather", "input": {"city": "Paris"}}}],
        )
        assert turns[2] == ("user", [{"toolResult": {"toolUseId": "call_1", "content": [_text("sunny")]}}])

    def test_parallel_results_share_one_user_turn(self) -> None:
        turns = _turns(
            [
                {"role": "user", "content": "both"},
                {"role": "assistant", "content": "checking", "tool_calls": [_call("a"), _call("b")]},
                {"role": "tool", "tool_call_id": "a", "content": "x"},
                {"role": "tool", "tool_call_id": "b", "content": "y"},
            ]
        )
        assert [role for role, _ in turns] == ["user", "assistant", "user"]
        assert [b["toolResult"]["toolUseId"] for b in turns[2][1]] == ["a", "b"]  # type: ignore[index]
        assert [list(b) for b in turns[1][1]] == [["text"], ["toolUse"], ["toolUse"]]

    def test_text_after_tool_results_is_kept_apart_by_a_short_assistant_turn(self) -> None:
        turns = _turns(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "", "tool_calls": [_call()]},
                {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
                {"role": "user", "content": "thanks"},
            ]
        )
        assert [role for role, _ in turns] == ["user", "assistant", "user", "assistant", "user"]
        assert turns[3] == ("assistant", CONTINUE)
        assert turns[4] == ("user", [_text("thanks")])

    def test_text_before_tool_results_is_kept_apart_the_same_way(self) -> None:
        turns = _turns(
            [
                {"role": "user", "content": "q"},
                {"role": "tool", "tool_call_id": "call_1", "content": "late"},
            ]
        )
        assert [role for role, _ in turns] == ["user", "assistant", "user"]
        assert "toolResult" in turns[2][1][0]

    def test_a_tool_that_printed_nothing_still_reports(self) -> None:
        turns = _turns([{"role": "tool", "tool_call_id": "c", "content": ""}])
        assert turns == [("user", [{"toolResult": {"toolUseId": "c", "content": [_text("(no output)")]}}])]

    def test_a_tool_result_may_carry_an_image(self) -> None:
        content = [{"type": "text", "text": "shot"}, {"type": "image_url", "image_url": {"url": PNG}}]
        turns = _turns([{"role": "tool", "tool_call_id": "c", "content": content}])
        inner = turns[0][1][0]["toolResult"]["content"]  # type: ignore[index]
        assert inner == [_text("shot"), {"image": {"format": "png", "source": {"bytes": "iVBORw0KGgo="}}}]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("call.1:x", "call_1_x"), ("a b", "a_b"), ("", "tool_use_id"), (None, "tool_use_id"), ("ok-1_2", "ok-1_2")],
    )
    def test_a_call_id_is_cleaned_the_same_in_the_call_and_in_its_result(self, raw: object, expected: str) -> None:
        turns = _turns(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "", "tool_calls": [_call(raw)]},
                {"role": "tool", "tool_call_id": raw, "content": "r"},
            ]
        )
        assert turns[1][1][0]["toolUse"]["toolUseId"] == expected  # type: ignore[index]
        assert turns[2][1][0]["toolResult"]["toolUseId"] == expected  # type: ignore[index]

    def test_the_first_of_two_calls_with_one_id_is_kept(self) -> None:
        turns = _turns(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "", "tool_calls": [_call("d", arguments='{"city": "A"}'), _call("d")]},
                {"role": "tool", "tool_call_id": "d", "content": "one"},
                {"role": "tool", "tool_call_id": "d", "content": "two"},
            ]
        )
        assert turns[1][1] == [{"toolUse": {"toolUseId": "d", "name": "get_weather", "input": {"city": "A"}}}]
        assert turns[2][1] == [{"toolResult": {"toolUseId": "d", "content": [_text("one")]}}]

    @pytest.mark.parametrize("arguments", ["not json", "[1, 2]", "", None, "   ", 5])
    def test_arguments_that_are_no_object_become_an_empty_one(self, arguments: object) -> None:
        turns = _turns(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "", "tool_calls": [_call(arguments=arguments)]},
            ]
        )
        assert turns[1][1][0]["toolUse"]["input"] == {}  # type: ignore[index]

    def test_a_tool_name_is_written_in_the_api_alphabet(self) -> None:
        turns = _turns(
            [{"role": "user", "content": "q"}, {"role": "assistant", "content": "", "tool_calls": [_call(name="a.b")]}]
        )
        assert turns[1][1][0]["toolUse"]["name"] == encode_tool_name("a.b")  # type: ignore[index]

    def test_a_malformed_call_is_skipped(self) -> None:
        turns = _turns(
            [{"role": "user", "content": "q"}, {"role": "assistant", "content": "hm", "tool_calls": ["x", {"id": "1"}]}]
        )
        assert turns[1] == ("assistant", [_text("hm")])


class TestReasoningReplay:
    def test_signed_and_redacted_thinking_lead_the_turn_and_unsigned_thinking_is_dropped(self) -> None:
        blocks = [
            {"type": "thinking", "thinking": "hm", "signature": "sig"},
            {"type": "redacted_thinking", "data": "QUJD"},
            {"type": "thinking", "thinking": "unsigned"},
            "junk",
        ]
        turns = _turns(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "answer", "thinking_blocks": blocks, "tool_calls": [_call()]},
            ]
        )
        assert turns[1][1] == [
            {"reasoningContent": {"reasoningText": {"text": "hm", "signature": "sig"}}},
            {"reasoningContent": {"redactedContent": "QUJD"}},
            _text("answer"),
            {"toolUse": {"toolUseId": "call_1", "name": "get_weather", "input": {"city": "Paris"}}},
        ]


class TestMedia:
    @pytest.mark.parametrize(
        ("media", "fmt"), [("image/png", "png"), ("image/jpeg", "jpeg"), ("image/jpg", "jpeg"), ("IMAGE/WEBP", "webp")]
    )
    def test_a_base64_image_is_sent_as_bytes_with_its_format(self, media: str, fmt: str) -> None:
        part = {"type": "image_url", "image_url": {"url": f"data:{media};base64,AAAA"}}
        assert _turns([{"role": "user", "content": [part]}])[0][1] == [
            {"image": {"format": fmt, "source": {"bytes": "AAAA"}}}
        ]

    def test_an_image_url_given_as_a_bare_string_is_read(self) -> None:
        assert _turns([{"role": "user", "content": [{"type": "image_url", "image_url": PNG}]}])[0][1][0] == {
            "image": {"format": "png", "source": {"bytes": "iVBORw0KGgo="}}
        }

    @pytest.mark.parametrize(
        "url", ["https://example.com/a.png", "data:image/tiff;base64,AAAA", "data:image/png,not-base64", "", None]
    )
    def test_an_image_converse_cannot_take_is_dropped_with_a_warning(
        self, url: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        part = {"type": "image_url", "image_url": {"url": url}}
        with caplog.at_level(logging.WARNING):
            turns = _turns([{"role": "user", "content": [{"type": "text", "text": "see"}, part]}])
        assert turns == [("user", [_text("see")])]
        assert "Dropping an image" in caplog.text

    def test_a_document_is_named_by_its_content_so_one_file_has_one_name(self) -> None:
        def document(data: str) -> Message:
            return {"type": "file", "file": {"file_data": f"data:application/pdf;base64,{data}"}}

        blocks = _turns([{"role": "user", "content": [document("AAAA"), document("AAAA"), document("BBBB")]}])[0][1]
        names = [b["document"]["name"] for b in blocks]  # type: ignore[index]
        assert names[0] == names[1] != names[2]
        assert all(re.fullmatch(r"document-[0-9a-f]{12}", n) for n in names)
        assert blocks[0]["document"]["format"] == "pdf"  # type: ignore[index]
        assert blocks[0]["document"]["source"] == {"bytes": "AAAA"}  # type: ignore[index]

    @pytest.mark.parametrize(
        ("media", "fmt"),
        [("text/csv", "csv"), ("text/plain", "txt"), ("text/markdown", "md"), ("text/html", "html")],
    )
    def test_document_types_map_to_converse_formats(self, media: str, fmt: str) -> None:
        part = {"type": "file", "file": {"file_data": f"data:{media};base64,AAAA"}}
        assert _turns([{"role": "user", "content": [part]}])[0][1][0]["document"]["format"] == fmt  # type: ignore[index]

    @pytest.mark.parametrize("file", [{"file_data": "data:application/zip;base64,AAAA"}, {"file_id": "f1"}, "x", None])
    def test_a_document_converse_cannot_take_is_dropped(self, file: object, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            turns = _turns(
                [{"role": "user", "content": [{"type": "file", "file": file}, {"type": "text", "text": "x"}]}]
            )
        assert turns == [("user", [_text("x")])]
        assert "Dropping a file" in caplog.text

    def test_a_part_of_an_unknown_type_is_dropped_with_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            turns = _turns([{"role": "user", "content": [{"type": "input_audio"}, {"type": "text", "text": "x"}]}])
        assert turns == [("user", [_text("x")])]
        assert "unsupported type" in caplog.text


class TestCachePoints:
    def test_a_marked_message_is_followed_by_a_cache_point(self) -> None:
        turns = _turns([{"role": "user", "content": "big", "cache_control": {"type": "ephemeral"}}])
        assert turns[0][1] == [_text("big"), {"cachePoint": {"type": "default"}}]

    def test_a_marked_part_is_followed_by_a_cache_point(self) -> None:
        parts = [{"type": "text", "text": "a"}, {"type": "text", "text": "b", "cache_control": {"type": "ephemeral"}}]
        assert _turns([{"role": "user", "content": parts}])[0][1] == [
            _text("a"),
            _text("b"),
            {"cachePoint": {"type": "default"}},
        ]

    def test_a_marked_system_prompt_keeps_its_cache_point(self) -> None:
        system = to_turns([{"role": "system", "content": "s", "cache_control": {"type": "ephemeral"}}], CLAUDE)[0]
        assert system == [_text("s"), {"cachePoint": {"type": "default"}}]

    def test_a_tool_result_keeps_its_cache_point_beside_it_not_inside(self) -> None:
        message = {"role": "tool", "tool_call_id": "c", "content": "r", "cache_control": {"type": "ephemeral"}}
        assert _turns([message])[0][1] == [
            {"toolResult": {"toolUseId": "c", "content": [_text("r")]}},
            {"cachePoint": {"type": "default"}},
        ]

    @pytest.mark.parametrize(
        ("model", "marker", "point"),
        [
            (CLAUDE_4_5, {"ttl": "1h"}, {"type": "default", "ttl": "1h"}),
            (CLAUDE_4_5, {"ttl": "5m"}, {"type": "default", "ttl": "5m"}),
            (CLAUDE_4_5, {"ttl": "30m"}, {"type": "default"}),
            (CLAUDE_4_5, {}, {"type": "default"}),
            (CLAUDE, {"ttl": "1h"}, {"type": "default"}),
            (NOVA, {"ttl": "1h"}, {"type": "default"}),
            ("us.anthropic.claude-opus-4-7-20991231-v1:0", {"ttl": "1h"}, {"type": "default", "ttl": "1h"}),
        ],
    )
    def test_a_lifetime_is_sent_only_where_the_model_takes_one(
        self, model: str, marker: dict[str, object], point: dict[str, object]
    ) -> None:
        assert cache_point({"cache_control": marker}, model) == [{"cachePoint": point}]

    def test_a_bare_marker_is_a_default_cache_point_and_no_marker_is_none(self) -> None:
        assert cache_point({"cache_control": True}, CLAUDE_4_5) == [{"cachePoint": {"type": "default"}}]
        assert cache_point({}, CLAUDE_4_5) == []
        assert cache_point({"cache_control": None}, CLAUDE_4_5) == []


_KINDS: dict[str, Message] = {
    "user": {"role": "user", "content": "u"},
    "assistant": {"role": "assistant", "content": "a"},
    "calls": {"role": "assistant", "content": "", "tool_calls": [_call("t1"), _call("t2")]},
    "result": {"role": "tool", "tool_call_id": "t1", "content": "r"},
    "system": {"role": "system", "content": "s"},
    "blank-user": {"role": "user", "content": " "},
    "blank-assistant": {"role": "assistant", "content": ""},
}


def _violations(history: tuple[str, ...]) -> list[str]:
    system, turns = to_turns([_KINDS[k] for k in history], CLAUDE)
    roles = [role for role, _ in turns]
    found: list[str] = []
    if roles[0] != "user" or roles[-1] != "user":
        found.append("a conversation opens and ends with the user")
    if any(a == b for a, b in itertools.pairwise(roles)):
        found.append("turns alternate")
    if not all(blocks for _, blocks in turns):
        found.append("no turn is empty")
    if not all("text" in b or "cachePoint" in b for b in system):
        found.append("the system prompt is text")
    for role, blocks in turns:
        kinds = {next(iter(b)) for b in blocks}
        if "toolUse" in kinds and role != "assistant":
            found.append("a tool call belongs to the assistant")
        if "toolResult" in kinds and role != "user":
            found.append("a tool result belongs to the user")
        if "toolResult" in kinds and kinds & {"text", "image", "document"}:
            found.append("conversation blocks and tool results never share a user turn")
        if any("text" in b and not str(b["text"]).strip() for b in blocks):
            found.append("blank text is rejected by the API")
    json.dumps(turns)
    return [f"{'+'.join(history) or 'empty'}: {rule}" for rule in dict.fromkeys(found)]


def test_every_short_history_becomes_a_valid_conversation() -> None:
    """All 2801 histories of up to four messages, of the seven kinds a conversation holds."""
    histories = [h for size in range(5) for h in itertools.product(_KINDS, repeat=size)]
    assert [v for history in histories for v in _violations(history)] == []
