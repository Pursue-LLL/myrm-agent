"""Tests for the tool-source helpers: the citation sources of a tool result leave the text the model reads and are
stored with the number the model read each under.

[POS]
Unit level: which results are split, what the model reads afterwards, what travels in additional_kwargs, how the
numbers are stamped. The interceptor wiring and the path to the SSE ``sources`` event are covered in
test_tool_sources_pipeline.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares.tooling.tool_sources_hoisting import (
    TOOL_SOURCES_KWARG,
    hoist_tool_sources,
    stamp_source_indexes,
)

SOURCES: list[dict[str, object]] = [
    {"url": "https://a.test/post", "title": "A", "snippet": "first"},
    {"url": "https://b.test/post", "title": "B", "snippet": "second"},
]


def _message(payload: object, **fields: object) -> ToolMessage:
    return ToolMessage(content=json.dumps(payload, ensure_ascii=False), name="a_tool", tool_call_id="call_1", **fields)


def _hoisted(message: ToolMessage) -> ToolMessage:
    result = hoist_tool_sources(message)
    assert isinstance(result, ToolMessage)
    return result


class TestAnEnvelopeWithOnlySources:
    def test_the_model_reads_the_bare_content(self) -> None:
        result = _hoisted(_message({"content": "the answer text", "metadata": {"sources": SOURCES}}))

        assert result.content == "the answer text"

    def test_the_sources_travel_in_additional_kwargs(self) -> None:
        result = _hoisted(_message({"content": "text", "metadata": {"sources": SOURCES}}))

        assert result.additional_kwargs[TOOL_SOURCES_KWARG] == SOURCES

    def test_content_keeps_its_own_newlines_quotes_and_non_ascii_characters(self) -> None:
        content = 'line one\n"quoted" 中文 <<<UNTRUSTED_DATA id="ab12">>>'

        result = _hoisted(_message({"content": content, "metadata": {"sources": SOURCES}}))

        assert result.content == content

    def test_an_empty_sources_list_is_stripped_and_leaves_no_kwarg(self) -> None:
        result = _hoisted(_message({"content": "no hits", "metadata": {"sources": []}}))

        assert result.content == "no hits"
        assert TOOL_SOURCES_KWARG not in result.additional_kwargs


class TestAnEnvelopeWithMoreThanSources:
    def test_the_model_reads_the_envelope_without_its_sources_in_the_original_order(self) -> None:
        payload = {
            "content": "page text",
            "metadata": {"operation": "fetch_full_content", "sources": SOURCES, "truncated": False},
            "evicted_ref": None,
        }

        result = _hoisted(_message(payload))

        assert result.content == json.dumps(
            {
                "content": "page text",
                "metadata": {"operation": "fetch_full_content", "truncated": False},
                "evicted_ref": None,
            },
            ensure_ascii=False,
        )
        assert result.additional_kwargs[TOOL_SOURCES_KWARG] == SOURCES

    def test_an_envelope_left_with_only_a_sibling_key_drops_the_emptied_metadata(self) -> None:
        result = _hoisted(_message({"content": "text", "metadata": {"sources": SOURCES}, "evicted_ref": "out.txt"}))

        assert json.loads(str(result.content)) == {"content": "text", "evicted_ref": "out.txt"}

    def test_non_ascii_text_stays_unescaped(self) -> None:
        result = _hoisted(_message({"content": "中文内容", "metadata": {"sources": SOURCES, "total_calls": 2}}))

        assert "中文内容" in str(result.content)
        assert json.loads(str(result.content))["metadata"] == {"total_calls": 2}


class TestTheMessageItself:
    def test_other_additional_kwargs_are_kept(self) -> None:
        message = _message({"content": "text", "metadata": {"sources": SOURCES}}, additional_kwargs={"flag": 1})

        result = _hoisted(message)

        assert result.additional_kwargs == {"flag": 1, TOOL_SOURCES_KWARG: SOURCES}

    def test_the_identity_of_the_message_is_kept(self) -> None:
        message = _message({"content": "text", "metadata": {"sources": SOURCES}}, id="msg-7", status="success")

        result = _hoisted(message)

        assert (result.id, result.tool_call_id, result.name, result.status) == ("msg-7", "call_1", "a_tool", "success")

    def test_the_given_message_is_not_modified(self) -> None:
        raw = json.dumps({"content": "text", "metadata": {"sources": SOURCES}})
        message = ToolMessage(content=raw, name="a_tool", tool_call_id="call_1")

        hoist_tool_sources(message)

        assert message.content == raw
        assert message.additional_kwargs == {}

    def test_hoisting_twice_changes_nothing_more(self) -> None:
        once = _hoisted(_message({"content": "text", "metadata": {"sources": SOURCES, "operation": "x"}}))

        assert hoist_tool_sources(once) is once


class TestResultsThatAreLeftAlone:
    @pytest.mark.parametrize(
        "text",
        [
            "plain text result",
            '"sources" quoted in prose, not JSON',
            json.dumps([{"sources": 1}]),
            json.dumps({"result": "ok", "metadata": {"sources": SOURCES}}),
            json.dumps({"content": "x"}),
            json.dumps({"content": "x", "metadata": {}}),
            json.dumps({"content": "x", "metadata": {"note": 'has "sources" inside'}}),
            json.dumps({"content": "x", "metadata": {"sources": "https://a.test"}}),
            json.dumps({"content": "x", "metadata": ["sources"]}),
            json.dumps({"content": ["block"], "metadata": {"sources": SOURCES}}),
            '{"content": "x", "metadata": {"sources": [',
            json.dumps({"content": "x", "metadata": {"sources": SOURCES}}) + "\n\nLoop detected: change approach",
        ],
    )
    def test_text_that_is_not_such_an_envelope_is_returned_as_it_is(self, text: str) -> None:
        message = ToolMessage(content=text, name="a_tool", tool_call_id="call_1")

        assert hoist_tool_sources(message) is message

    def test_json_nested_too_deeply_to_parse_is_returned_as_it_is(self) -> None:
        depth = 100_000
        text = '{"a":' * depth + '"sources"' + "}" * depth
        message = ToolMessage(content=text, name="a_tool", tool_call_id="call_1")

        assert hoist_tool_sources(message) is message

    def test_a_content_block_list_is_returned_as_it_is(self) -> None:
        message = ToolMessage(
            content=[{"type": "text", "text": '{"content": "x", "metadata": {"sources": [{"url": "u"}]}}'}],
            name="a_tool",
            tool_call_id="call_1",
        )

        assert hoist_tool_sources(message) is message

    def test_an_error_result_is_returned_as_it_is(self) -> None:
        message = _message({"content": "boom", "metadata": {"sources": SOURCES}}, status="error")

        assert hoist_tool_sources(message) is message

    def test_a_graph_command_is_returned_as_it_is(self) -> None:
        command: Command[object] = Command(update={"k": "v"})

        assert hoist_tool_sources(command) is command


NUMBERS = {"https://a.test/post": 4, "https://b.test/post": 7}


def _number_of(source: Mapping[str, object]) -> int:
    return NUMBERS[str(source["url"])]


def _hoisted_message() -> ToolMessage:
    return _hoisted(_message({"content": "text", "metadata": {"sources": SOURCES}}))


def _stamped(message: ToolMessage) -> ToolMessage:
    result = stamp_source_indexes(message, _number_of)
    assert isinstance(result, ToolMessage)
    return result


class TestStampSourceIndexes:
    """The stored tool message records the number each source was read under, which is its card's index."""

    def test_each_source_carries_the_number_the_run_gave_it(self) -> None:
        result = _stamped(_hoisted_message())

        assert result.additional_kwargs[TOOL_SOURCES_KWARG] == [
            {**source, "index": _number_of(source)} for source in SOURCES
        ]

    def test_the_run_is_asked_once_per_source_in_order(self) -> None:
        asked: list[Mapping[str, object]] = []

        def record(source: Mapping[str, object]) -> int:
            asked.append(source)
            return len(asked)

        result = stamp_source_indexes(_hoisted_message(), record)

        assert asked == SOURCES
        assert isinstance(result, ToolMessage)
        assert [source["index"] for source in result.additional_kwargs[TOOL_SOURCES_KWARG]] == [1, 2]

    def test_a_stale_index_in_a_source_is_replaced_by_the_runs_number(self) -> None:
        message = _message({"content": "text", "metadata": {"sources": [{**SOURCES[0], "index": 99}]}})

        result = _stamped(_hoisted(message))

        assert result.additional_kwargs[TOOL_SOURCES_KWARG][0]["index"] == 4

    def test_what_the_model_reads_and_the_rest_of_the_message_stay_as_they_were(self) -> None:
        message = _hoisted(
            _message({"content": "text", "metadata": {"sources": SOURCES}}, additional_kwargs={"flag": 1}, id="msg-7")
        )

        result = _stamped(message)

        assert result.content == message.content
        assert (result.id, result.tool_call_id, result.name) == ("msg-7", "call_1", "a_tool")
        assert result.additional_kwargs["flag"] == 1

    def test_the_given_message_is_not_modified(self) -> None:
        message = _hoisted_message()

        _stamped(message)

        assert message.additional_kwargs[TOOL_SOURCES_KWARG] == SOURCES

    def test_an_entry_that_is_not_a_source_dict_is_kept_as_it_is(self) -> None:
        message = ToolMessage(
            content="text",
            name="a_tool",
            tool_call_id="call_1",
            additional_kwargs={TOOL_SOURCES_KWARG: ["x", SOURCES[0]]},
        )

        result = _stamped(message)

        assert result.additional_kwargs[TOOL_SOURCES_KWARG] == ["x", {**SOURCES[0], "index": 4}]


class TestResultsWithNothingToStamp:
    def test_a_message_without_hoisted_sources_is_returned_as_it_is(self) -> None:
        message = ToolMessage(content="plain", name="a_tool", tool_call_id="call_1")

        assert stamp_source_indexes(message, _number_of) is message

    @pytest.mark.parametrize("sources", [[], "https://a.test", None])
    def test_an_empty_or_malformed_sources_value_is_returned_as_it_is(self, sources: object) -> None:
        message = ToolMessage(
            content="text", name="a_tool", tool_call_id="call_1", additional_kwargs={TOOL_SOURCES_KWARG: sources}
        )

        assert stamp_source_indexes(message, _number_of) is message

    def test_a_run_without_source_numbering_leaves_the_message_as_it_is(self) -> None:
        message = _hoisted_message()

        assert stamp_source_indexes(message, None) is message

    def test_a_graph_command_is_returned_as_it_is(self) -> None:
        command: Command[object] = Command(update={"k": "v"})

        assert stamp_source_indexes(command, _number_of) is command
