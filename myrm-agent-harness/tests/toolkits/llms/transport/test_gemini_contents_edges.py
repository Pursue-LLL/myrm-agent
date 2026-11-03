"""Gemini ``contents`` edges: parts the API takes inline or not at all, and calls with arguments it cannot read."""

from __future__ import annotations

import logging

import pytest

from myrm_agent_harness.toolkits.llms.transport import gemini_generate
from myrm_agent_harness.toolkits.llms.transport.gemini_schema import _MAX_DEPTH, to_gemini_schema
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Message = dict[str, object]

MODEL = "gemini-2.5-pro"
PDF = "data:application/pdf;base64,JVBERg=="


def _contents(messages: list[Message]) -> list[dict[str, object]]:
    route = resolve_route(f"gemini/{MODEL}", api_key="k")
    body = gemini_generate.prepare(route, messages, {}).body
    assert body is not None
    contents = body["contents"]
    assert isinstance(contents, list)
    return contents


def _user_parts(content: object) -> list[dict[str, object]]:
    turn = _contents([{"role": "user", "content": content}])[0]
    parts = turn["parts"]
    assert isinstance(parts, list)
    return parts


class TestParts:
    def test_a_file_part_with_inline_data_keeps_its_media_type(self) -> None:
        parts = _user_parts([{"type": "text", "text": "read"}, {"type": "file", "file": {"file_data": PDF}}])

        assert parts == [{"text": "read"}, {"inlineData": {"mimeType": "application/pdf", "data": "JVBERg=="}}]

    @pytest.mark.parametrize(
        "part",
        [{"type": "file", "file": {"file_data": "https://example.test/a.pdf"}}, {"type": "file", "file": 3}],
        ids=["remote-file", "file-not-a-mapping"],
    )
    def test_a_file_the_api_cannot_read_inline_is_left_out(self, part: Message) -> None:
        assert _user_parts([{"type": "text", "text": "read"}, part]) == [{"text": "read"}]

    def test_bare_strings_are_text_and_empty_ones_vanish(self) -> None:
        assert _user_parts(["one", "", {"type": "text", "text": "two"}]) == [{"text": "one"}, {"text": "two"}]

    def test_a_blank_text_part_is_dropped_quietly_but_an_unsupported_type_is_named(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            parts = _user_parts(
                [{"type": "text", "text": ""}, {"type": "text", "text": "kept"}, {"type": "input_audio", "x": 1}]
            )

        assert parts == [{"text": "kept"}]
        assert "input_audio" in caplog.text
        assert "'text'" not in caplog.text, "blank text is not an unsupported part"


class TestToolHistory:
    def test_a_call_without_a_function_is_skipped_and_unreadable_arguments_become_an_empty_object(self) -> None:
        calls = [
            {"id": "c0", "type": "function"},
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{not json"}},
        ]

        contents = _contents(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "", "tool_calls": calls},
            ]
        )

        assert contents[1] == {"role": "model", "parts": [{"functionCall": {"name": "f", "args": {}}}]}

    def test_an_assistant_turn_with_nothing_to_say_adds_no_turn(self) -> None:
        contents = _contents(
            [{"role": "user", "content": "a"}, {"role": "assistant", "content": ""}, {"role": "user", "content": "b"}]
        )

        assert contents == [{"role": "user", "parts": [{"text": "a"}, {"text": "b"}]}]


class TestSchema:
    def test_a_union_of_several_types_keeps_every_live_variant_and_turns_null_into_nullable(self) -> None:
        schema = to_gemini_schema(
            {
                "type": "object",
                "properties": {"id": {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]}},
            }
        )

        assert schema["properties"] == {"id": {"anyOf": [{"type": "string"}, {"type": "integer"}], "nullable": True}}

    def test_a_property_that_is_not_a_schema_object_becomes_an_unconstrained_one(self) -> None:
        schema = to_gemini_schema({"type": "object", "properties": {"anything": True}})

        assert schema["properties"] == {"anything": {}}

    def test_a_schema_nested_beyond_the_depth_limit_is_cut_not_followed_forever(self) -> None:
        node: dict[str, object] = {"type": "string"}
        for _ in range(20):
            node = {"type": "object", "properties": {"next": node}}

        depth = 0
        cursor: object = to_gemini_schema(node)
        while isinstance(cursor, dict) and cursor.get("properties"):
            cursor = cursor["properties"]["next"]  # type: ignore[index]
            depth += 1

        assert depth == _MAX_DEPTH + 1, "the converter stops descending at its depth limit"
