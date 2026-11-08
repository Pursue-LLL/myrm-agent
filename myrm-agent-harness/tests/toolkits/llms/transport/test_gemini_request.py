"""Gemini ``contents`` rules: the call ids and signatures Gemini 3 demands and the role alternation the API enforces."""

from __future__ import annotations

import base64
import json
from itertools import pairwise

import pytest

from myrm_agent_harness.toolkits.llms.transport import gemini_generate
from myrm_agent_harness.toolkits.llms.transport.gemini_contents import INTERRUPTED_REPLY
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Message = dict[str, object]
Turn = dict[str, object]
Part = dict[str, object]

GEMINI_3 = "gemini-3-pro-preview"
GEMINI_4 = "gemini-4-argon"
GEMINI_2 = "gemini-2.5-pro"
PNG = "data:image/png;base64,iVBORw0KGgo="
_SHOT = [{"type": "text", "text": "shot"}, {"type": "image_url", "image_url": {"url": PNG}}]
_INLINE = {"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgo="}}
PLACEHOLDER_SIGNATURE = base64.b64encode(b"skip_thought_signature_validator").decode("ascii")


def _body(model: str, messages: list[Message] | None = None, **params: object) -> dict[str, object]:
    route = resolve_route(f"gemini/{model}", api_key="k")
    history = messages if messages is not None else [{"role": "user", "content": "hi"}]
    return gemini_generate.prepare(route, history, params).body


def _contents(model: str, messages: list[Message]) -> list[Turn]:
    contents = _body(model, messages)["contents"]
    assert isinstance(contents, list)
    return contents


def _call(call_id: str, name: str = "get_weather", **arguments: object) -> dict[str, object]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def _result(call_id: str, content: str = "sunny") -> Message:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _parts(turn: Turn) -> list[Part]:
    parts = turn["parts"]
    assert isinstance(parts, list)
    return parts


def _tool_turn(call_id: str) -> list[Message]:
    return [
        {"role": "user", "content": "weather?"},
        {"role": "assistant", "content": "", "tool_calls": [_call(call_id, city="Paris")]},
        _result(call_id),
    ]


class TestFunctionCallsOfGemini3:
    def test_a_call_carries_its_id_and_a_placeholder_signature_when_the_model_did_not_sign_it(self) -> None:
        call = _parts(_contents(GEMINI_3, _tool_turn("call_1"))[1])[0]
        assert call == {
            "functionCall": {"name": "get_weather", "args": {"city": "Paris"}, "id": "call_1"},
            "thoughtSignature": PLACEHOLDER_SIGNATURE,
        }

    def test_the_signature_the_model_issued_travels_in_the_call_id_and_comes_back_unchanged(self) -> None:
        call = _parts(_contents(GEMINI_3, _tool_turn("call_1__thought__abc"))[1])[0]
        assert call["thoughtSignature"] == "abc"
        assert call["functionCall"]["id"] == "call_1"  # type: ignore[index]

    def test_the_response_names_the_call_it_answers(self) -> None:
        response = _parts(_contents(GEMINI_3, _tool_turn("call_1__thought__abc"))[2])[0]["functionResponse"]
        assert response == {"name": "get_weather", "response": {"content": "sunny"}, "id": "call_1"}

    def test_an_empty_id_is_left_off(self) -> None:
        call = _parts(_contents(GEMINI_3, _tool_turn(""))[1])[0]["functionCall"]
        assert "id" not in call  # type: ignore[operator]


class TestLaterGenerations:
    def test_a_generation_after_gemini_3_takes_the_same_ids_and_signatures(self) -> None:
        call = _parts(_contents(GEMINI_4, _tool_turn("call_1"))[1])[0]
        assert call["functionCall"]["id"] == "call_1"  # type: ignore[index]
        assert call["thoughtSignature"] == PLACEHOLDER_SIGNATURE


class TestFunctionCallsOfEarlierModels:
    def test_a_call_takes_neither_an_id_nor_a_placeholder_signature(self) -> None:
        call = _parts(_contents(GEMINI_2, _tool_turn("call_1"))[1])[0]
        assert call == {"functionCall": {"name": "get_weather", "args": {"city": "Paris"}}}

    def test_a_signature_the_model_issued_is_still_returned(self) -> None:
        call = _parts(_contents(GEMINI_2, _tool_turn("call_1__thought__abc"))[1])[0]
        assert call["thoughtSignature"] == "abc"
        assert "id" not in call["functionCall"]  # type: ignore[operator]

    def test_the_response_has_no_id(self) -> None:
        response = _parts(_contents(GEMINI_2, _tool_turn("call_1"))[2])[0]["functionResponse"]
        assert response == {"name": "get_weather", "response": {"content": "sunny"}}


class TestFunctionResponses:
    def test_a_json_object_result_is_the_response_itself(self) -> None:
        turns = [*_tool_turn("c")[:2], _result("c", '{"temp": 21}')]
        assert _parts(_contents(GEMINI_2, turns)[2])[0]["functionResponse"]["response"] == {"temp": 21}  # type: ignore[index]

    @pytest.mark.parametrize("content", ["plain text", "[1, 2]", "42", ""])
    def test_anything_else_is_wrapped(self, content: str) -> None:
        turns = [*_tool_turn("c")[:2], _result("c", content)]
        assert _parts(_contents(GEMINI_2, turns)[2])[0]["functionResponse"]["response"] == {"content": content}  # type: ignore[index]

    def test_parallel_results_share_one_user_turn(self) -> None:
        turns: list[Message] = [
            {"role": "user", "content": "weather?"},
            {"role": "assistant", "content": "", "tool_calls": [_call("a", city="Paris"), _call("b", city="Rome")]},
            _result("a", "sunny"),
            _result("b", "rainy"),
        ]
        contents = _contents(GEMINI_2, turns)
        assert [t["role"] for t in contents] == ["user", "model", "user"]
        assert [p["functionResponse"]["response"]["content"] for p in _parts(contents[2])] == ["sunny", "rainy"]  # type: ignore[index]


class TestMediaInFunctionResponses:
    """A screenshot a tool returns: inside the function response on Gemini 3 and later, beside it on earlier models."""

    @staticmethod
    def _tool_turn_parts(model: str, content: object) -> list[Part]:
        history = [*_tool_turn("c")[:2], {"role": "tool", "tool_call_id": "c", "content": content}]
        return _parts(_contents(model, history)[2])

    def test_gemini_3_gets_inline_media_inside_the_response(self) -> None:
        (part,) = self._tool_turn_parts(GEMINI_3, _SHOT)
        assert part["functionResponse"]["response"] == {"content": "shot"}  # type: ignore[index]
        assert part["functionResponse"]["parts"] == [_INLINE]  # type: ignore[index]

    def test_earlier_models_get_the_media_beside_the_response(self) -> None:
        response, media = self._tool_turn_parts(GEMINI_2, _SHOT)
        assert response == {"functionResponse": {"name": "get_weather", "response": {"content": "shot"}}}
        assert media == _INLINE

    def test_media_given_by_address_rides_beside_the_response_on_every_generation(self) -> None:
        shot = [{"type": "image_url", "image_url": {"url": "https://example.com/shot.png"}}]
        for model in (GEMINI_2, GEMINI_3):
            response, media = self._tool_turn_parts(model, shot)
            assert "parts" not in response["functionResponse"]  # type: ignore[operator]
            assert media == {"fileData": {"fileUri": "https://example.com/shot.png", "mimeType": "image/png"}}

    def test_a_text_only_result_has_no_media(self) -> None:
        for model in (GEMINI_2, GEMINI_3):
            (part,) = self._tool_turn_parts(model, [{"type": "text", "text": "sunny"}])
            assert "parts" not in part["functionResponse"]  # type: ignore[operator]

    def test_media_of_parallel_results_stays_in_the_one_response_turn(self) -> None:
        history: list[Message] = [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": f"c{i}", "type": "function", "function": {"name": "shot", "arguments": "{}"}} for i in (1, 2)
                ],
            },
            *({"role": "tool", "tool_call_id": f"c{i}", "content": _SHOT} for i in (1, 2)),
        ]
        turns = _contents(GEMINI_2, history)
        assert [turn["role"] for turn in turns] == ["user", "model", "user"]
        kinds = [next(iter(part)) for part in _parts(turns[2])]
        assert kinds == ["functionResponse", "inlineData", "functionResponse", "inlineData"]


class TestRoleAlternation:
    """Gemini rejects adjacent turns of one role, and Gemini 3 misreads a user message folded into a tool result."""

    def test_a_user_message_after_a_tool_result_gets_a_model_turn_in_between(self) -> None:
        turns = [*_tool_turn("c"), {"role": "user", "content": "thanks"}]
        contents = _contents(GEMINI_3, turns)
        assert [t["role"] for t in contents] == ["user", "model", "user", "model", "user"]
        assert _parts(contents[3]) == [{"text": INTERRUPTED_REPLY}]
        assert _parts(contents[4]) == [{"text": "thanks"}]

    def test_a_tool_result_after_a_user_message_gets_one_as_well(self) -> None:
        turns: list[Message] = [{"role": "user", "content": "hi"}, _result("c")]
        assert [t["role"] for t in _contents(GEMINI_2, turns)] == ["user", "model", "user"]

    def test_user_messages_in_a_row_merge(self) -> None:
        turns: list[Message] = [{"role": "user", "content": "one"}, {"role": "user", "content": "two"}]
        contents = _contents(GEMINI_2, turns)
        assert len(contents) == 1
        assert [p["text"] for p in _parts(contents[0])] == ["one", "two"]

    def test_assistant_messages_in_a_row_merge(self) -> None:
        turns: list[Message] = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "one"},
            {"role": "assistant", "content": "two"},
        ]
        contents = _contents(GEMINI_2, turns)
        assert [t["role"] for t in contents] == ["user", "model"]
        assert [p["text"] for p in _parts(contents[1])] == ["one", "two"]

    def test_a_long_mixed_history_always_alternates(self) -> None:
        turns: list[Message] = [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "", "tool_calls": [_call("1")]},
            _result("1"),
            {"role": "user", "content": "c"},
            {"role": "assistant", "content": "", "tool_calls": [_call("2")]},
            _result("2"),
            _result("2"),
            {"role": "assistant", "content": "done"},
            {"role": "user", "content": "d"},
        ]
        roles = [t["role"] for t in _contents(GEMINI_3, turns)]
        assert all(a != b for a, b in pairwise(roles)), roles


class TestSystemInstruction:
    def test_system_and_developer_messages_become_the_system_instruction(self) -> None:
        route = resolve_route(f"gemini/{GEMINI_2}", api_key="k")
        turns: list[Message] = [
            {"role": "system", "content": "be brief"},
            {"role": "developer", "content": [{"type": "text", "text": "answer in French"}]},
            {"role": "user", "content": "hi"},
        ]
        body = gemini_generate.prepare(route, turns, {}).body
        assert body["system_instruction"] == {"parts": [{"text": "be brief"}, {"text": "answer in French"}]}
        assert [t["role"] for t in body["contents"]] == ["user"]  # type: ignore[attr-defined]


class TestThinkingConfig:
    @pytest.mark.parametrize(
        ("model", "effort", "expected"),
        [
            (GEMINI_2, "high", {"includeThoughts": True, "thinkingBudget": 4096}),
            (GEMINI_2, "medium", {"includeThoughts": True, "thinkingBudget": 2048}),
            (GEMINI_2, "low", {"includeThoughts": True, "thinkingBudget": 1024}),
            (GEMINI_3, "high", {"includeThoughts": True, "thinkingLevel": "high"}),
            (GEMINI_3, "xhigh", {"includeThoughts": True, "thinkingLevel": "high"}),
            (GEMINI_4, "low", {"includeThoughts": True, "thinkingLevel": "low"}),
            ("gemini-flash-latest", "low", {"includeThoughts": True, "thinkingLevel": "low"}),
        ],
    )
    def test_effort_becomes_a_budget_or_a_level_by_generation(self, model: str, effort: str, expected: dict) -> None:
        assert _body(model, reasoning_effort=effort)["generationConfig"]["thinkingConfig"] == expected  # type: ignore[index]

    @pytest.mark.parametrize(
        ("model", "budget"),
        [("gemini-2.5-pro", 128), ("gemini-2.5-flash-lite", 512), ("gemini-2.5-flash", 1)],
    )
    def test_minimal_effort_is_the_smallest_budget_the_model_takes(self, model: str, budget: int) -> None:
        config = _body(model, reasoning_effort="minimal")["generationConfig"]["thinkingConfig"]  # type: ignore[index]
        assert config == {"includeThoughts": True, "thinkingBudget": budget}

    @pytest.mark.parametrize(
        ("model", "effort", "level"),
        [
            ("gemini-3-flash-preview", "minimal", "minimal"),
            ("gemini-3-flash-preview", "medium", "medium"),
            ("gemini-3-pro-preview", "minimal", "low"),
            ("gemini-3-pro-preview", "medium", "high"),
            ("gemini-3.1-pro-preview", "medium", "medium"),
            ("gemini-4-argon", "medium", "medium"),
            ("gemini-pro-latest", "medium", "high"),
        ],
    )
    def test_a_level_the_model_lacks_becomes_the_nearest_one_it_has(self, model: str, effort: str, level: str) -> None:
        config = _body(model, reasoning_effort=effort)["generationConfig"]["thinkingConfig"]  # type: ignore[index]
        assert config == {"includeThoughts": True, "thinkingLevel": level}

    @pytest.mark.parametrize("effort", ["none", "off", "disable", "disabled"])
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("gemini-2.5-flash", {"includeThoughts": False, "thinkingBudget": 0}),
            ("gemini-2.5-flash-lite", {"includeThoughts": False, "thinkingBudget": 0}),
            ("gemini-2.5-pro", {"includeThoughts": False, "thinkingBudget": 128}),
            ("gemini-3-pro-preview", {"includeThoughts": False, "thinkingLevel": "low"}),
            ("gemini-3-flash-preview", {"includeThoughts": False, "thinkingLevel": "minimal"}),
            ("gemini-flash-latest", {"includeThoughts": False, "thinkingLevel": "minimal"}),
        ],
    )
    def test_a_disabled_effort_switches_thinking_off_as_far_as_the_model_allows(
        self, model: str, effort: str, expected: dict
    ) -> None:
        assert _body(model, reasoning_effort=effort)["generationConfig"]["thinkingConfig"] == expected  # type: ignore[index]

    def test_no_effort_leaves_the_models_own_thinking_alone(self) -> None:
        assert "generationConfig" not in _body(GEMINI_3)


_TOOL = {"type": "function", "function": {"name": "get_weather", "parameters": {"type": "object", "properties": {}}}}
_SCHEMA = {"type": "json_schema", "json_schema": {"name": "r", "schema": {"type": "object", "properties": {}}}}


class TestJsonOutputBesideTools:
    """The API refuses JSON output beside function declarations before Gemini 3 and beside a forced call anywhere."""

    @staticmethod
    def _json_sent(model: str, **params: object) -> bool:
        config = _body(model, **params).get("generationConfig", {})
        return "responseMimeType" in config  # type: ignore[operator]

    def test_json_output_alone_is_sent_on_every_generation(self) -> None:
        assert self._json_sent(GEMINI_2, response_format=_SCHEMA)
        assert self._json_sent(GEMINI_3, response_format=_SCHEMA)

    def test_gemini_3_combines_json_output_with_tools(self) -> None:
        assert self._json_sent(GEMINI_3, response_format=_SCHEMA, tools=[_TOOL])

    def test_earlier_models_drop_json_output_when_tools_are_declared(self) -> None:
        body = _body(GEMINI_2, response_format=_SCHEMA, tools=[_TOOL])
        assert "generationConfig" not in body
        assert body["tools"]

    @pytest.mark.parametrize("choice", ["required", {"type": "function", "function": {"name": "get_weather"}}])
    def test_a_forced_call_drops_json_output_on_every_generation(self, choice: object) -> None:
        assert not self._json_sent(GEMINI_3, response_format=_SCHEMA, tools=[_TOOL], tool_choice=choice)
