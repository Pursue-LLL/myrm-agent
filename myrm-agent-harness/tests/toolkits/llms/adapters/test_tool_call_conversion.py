"""Contract tests of the inbound tool-call conversion in ``adapters/tool_call_conversion``.

A provider's raw tool call becomes a call the agent may dispatch, or an ``invalid_tool_call`` the model can see and
retry; an unsafe parse never becomes executable.
"""

from __future__ import annotations

import json
from typing import cast

import pytest

from myrm_agent_harness.toolkits.llms.adapters.tool_call_conversion import (
    build_invalid_tool_call,
    convert_raw_tool_call_to_langchain,
    parse_tool_call_args_result,
    resolve_tool_schema,
)
from myrm_agent_harness.toolkits.llms.adapters.tool_call_parsers import ToolCallDict


def _raw(name: str, arguments: object, call_id: str = "call_1") -> ToolCallDict:
    """A wire tool call; ``arguments`` may be any value a provider could send."""
    return cast("ToolCallDict", {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}})


class TestResolveToolSchema:
    def test_nothing_is_resolved_without_schemas(self) -> None:
        assert resolve_tool_schema("echo", None) is None
        assert resolve_tool_schema("echo", {}) is None

    def test_the_exact_name_wins_over_the_namespace_stripped_one(self) -> None:
        schemas = {"ns:echo": {"which": "exact"}, "echo": {"which": "stripped"}}

        assert resolve_tool_schema("ns:echo", schemas) == {"which": "exact"}

    def test_a_namespace_prefix_is_stripped_to_find_the_schema(self) -> None:
        assert resolve_tool_schema("server:echo", {"echo": {"which": "stripped"}}) == {"which": "stripped"}

    def test_an_unknown_name_has_no_schema(self) -> None:
        assert resolve_tool_schema("server:other", {"echo": {}}) is None
        assert resolve_tool_schema("other", {"echo": {}}) is None


class TestParseToolCallArgsResult:
    def test_valid_json_is_parsed_with_the_standard_strategy(self) -> None:
        parsed, recovery = parse_tool_call_args_result('{"text": "hi"}', "echo")

        assert parsed == {"text": "hi"}
        assert recovery.safe
        assert recovery.strategy == "standard_json"

    def test_an_unsafe_parse_yields_no_arguments_at_all(self) -> None:
        parsed, recovery = parse_tool_call_args_result('{"path": "/etc/pas', "echo")

        assert parsed == {}
        assert not recovery.safe

    def test_a_degraded_parse_missing_a_required_field_is_not_handed_on_even_though_part_was_recovered(self) -> None:
        schema = {
            "parameters": {
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            }
        }

        parsed, recovery = parse_tool_call_args_result('noise "path": "a.txt" noise', "file_write", schema)

        assert recovery.strategy == "regex_fallback"
        assert recovery.args == {"path": "a.txt"}
        assert not recovery.safe
        assert parsed == {}

    def test_entities_are_decoded_only_when_the_caller_asks_for_it(self) -> None:
        raw = '{"cmd": "a &amp;&amp; b"}'

        assert parse_tool_call_args_result(raw, "echo")[0] == {"cmd": "a &amp;&amp; b"}
        assert parse_tool_call_args_result(raw, "echo", decode_html_entities=True)[0] == {"cmd": "a && b"}


class TestConvertRawToolCall:
    def test_a_well_formed_call_becomes_a_tool_call_with_its_metadata(self) -> None:
        tool_call, metadata = convert_raw_tool_call_to_langchain(_raw("echo", '{"text": "hi"}', "call_abc"))

        assert tool_call is not None
        assert (tool_call["name"], tool_call["args"], tool_call["id"]) == ("echo", {"text": "hi"}, "call_abc")
        assert metadata is not None
        assert metadata["tool_call_id"] == "call_abc"
        assert metadata["strategy"] == "standard_json"
        assert metadata["safe"] is True

    def test_a_namespace_prefix_is_dropped_from_the_name_of_the_call(self) -> None:
        tool_call, metadata = convert_raw_tool_call_to_langchain(_raw("outer:inner:echo", '{"text": "hi"}'))

        assert tool_call is not None
        assert tool_call["name"] == "echo"
        assert metadata is not None
        assert metadata["tool_name"] == "echo"

    def test_a_call_without_an_id_is_given_one(self) -> None:
        tool_call, _ = convert_raw_tool_call_to_langchain(_raw("echo", "{}", ""))

        assert tool_call is not None
        generated = tool_call["id"] or ""
        assert generated.startswith("call_")
        assert len(generated) == len("call_") + 24

    def test_an_unsafe_call_is_withheld_with_a_diagnosis_for_the_model(self) -> None:
        tool_call, metadata = convert_raw_tool_call_to_langchain(_raw("file_write_tool", '{"path": "/etc/pas'))

        assert tool_call is None
        assert metadata is not None
        assert metadata["safe"] is False
        assert "'file_write_tool'" in str(metadata["error"])
        assert "NOT executed" in str(metadata["error"])

    @pytest.mark.parametrize("raw", [cast("ToolCallDict", {}), cast("ToolCallDict", {"function": None})])
    def test_a_call_that_lacks_its_function_converts_to_nothing(self, raw: ToolCallDict) -> None:
        assert convert_raw_tool_call_to_langchain(raw) == (None, None)


class TestBuildInvalidToolCall:
    def test_the_raw_text_and_the_diagnosis_are_kept(self) -> None:
        metadata = {"tool_call_id": "call_9", "tool_name": "echo", "error": "could not be safely parsed"}

        declared = build_invalid_tool_call(_raw("ns:echo", '{"a": '), metadata)

        assert declared == {
            "type": "invalid_tool_call",
            "id": "call_9",
            "name": "echo",
            "args": '{"a": ',
            "error": "could not be safely parsed",
        }

    def test_dict_arguments_are_kept_as_json_with_sorted_keys(self) -> None:
        declared = build_invalid_tool_call(_raw("echo", {"b": 1, "a": 2}), {})

        assert declared["args"] == json.dumps({"a": 2, "b": 1})

    @pytest.mark.parametrize(("arguments", "kept"), [(None, ""), (7, "7")])
    def test_other_argument_types_are_kept_as_text(self, arguments: object, kept: str) -> None:
        assert build_invalid_tool_call(_raw("echo", arguments), {})["args"] == kept

    def test_what_the_metadata_lacks_comes_from_the_call(self) -> None:
        declared = build_invalid_tool_call(_raw("echo", "x", "call_7"), {})

        assert declared["id"] == "call_7"
        assert declared["name"] == "echo"
        assert declared["error"] == "Unsafe tool call arguments"

    def test_a_call_without_a_function_still_declares_an_empty_call(self) -> None:
        declared = build_invalid_tool_call(cast("ToolCallDict", {"id": "call_8"}), {})

        assert declared["args"] == ""
        assert declared["name"] == ""
        assert declared["id"] == "call_8"
