"""Bedrock structured output: a model that lists a native format is asked through ``outputConfig``, any other by tool.

The native format answers in plain text that already follows the schema, so reasoning and tools stay as the caller set
them. The API demands every object of the schema to be closed to extra properties, which is the one thing the wire
adds to the caller's schema.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.llms.catalog import register_model, store
from myrm_agent_harness.toolkits.llms.transport import bedrock_converse, bedrock_structured
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Body = dict[str, object]
NATIVE = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
JSON_TOOL = bedrock_structured.JSON_TOOL
SCHEMA: Body = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
WEATHER: Body = {
    "type": "function",
    "function": {"name": "get_weather", "description": "Weather", "parameters": {"type": "object"}},
}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})


def _body(model: str = NATIVE, **params: object) -> Body:
    route = resolve_route(f"bedrock/{model}", api_key="k")
    return bedrock_converse.prepare(route, [{"role": "user", "content": "hi"}], params).body


def _format(schema: Body | None = None, **fields: object) -> Body:
    return {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema or SCHEMA, **fields}}


def _definition(body: Body) -> Body:
    config = body["outputConfig"]
    assert isinstance(config, dict)
    assert config["textFormat"]["type"] == "json_schema"  # type: ignore[index]
    return config["textFormat"]["structure"]["jsonSchema"]  # type: ignore[index,no-any-return]


def _schema_of(body: Body) -> Body:
    return json.loads(_definition(body)["schema"])  # type: ignore[arg-type]


class TestNativeFormat:
    def test_the_schema_is_asked_as_an_output_format_and_no_tool_is_added(self) -> None:
        body = _body(response_format=_format(description="The result"))
        assert "toolConfig" not in body
        definition = _definition(body)
        assert definition["name"] == "answer"
        assert definition["description"] == "The result"
        assert json.loads(definition["schema"]) == {**SCHEMA, "additionalProperties": False}  # type: ignore[arg-type]

    def test_the_schema_travels_as_text_in_the_order_the_caller_wrote_it(self) -> None:
        text = _definition(_body(response_format=_format()))["schema"]
        assert text == json.dumps({**SCHEMA, "additionalProperties": False})

    @pytest.mark.parametrize("fields", [{}, {"description": None}, {"description": " "}])
    def test_a_description_is_sent_only_when_there_is_one(self, fields: Body) -> None:
        assert "description" not in _definition(_body(response_format=_format(**fields)))

    def test_a_schema_without_a_name_is_sent_without_one(self) -> None:
        body = _body(response_format={"type": "json_schema", "json_schema": {"schema": SCHEMA}})
        assert "name" not in _definition(body)

    def test_the_flat_schema_form_is_read_too(self) -> None:
        body = _body(response_format={"type": "json_schema", "response_schema": SCHEMA})
        assert _schema_of(body) == {**SCHEMA, "additionalProperties": False}
        assert {"name", "description"}.isdisjoint(_definition(body))

    @pytest.mark.parametrize(
        "response_format",
        [
            {"type": "json_object", "json_schema": {"name": "answer", "schema": SCHEMA}},
            {"type": "json_object", "response_schema": SCHEMA},
        ],
        ids=["holder", "flat"],
    )
    def test_a_json_object_format_that_carries_a_schema_is_asked_like_a_json_schema(
        self, response_format: Body
    ) -> None:
        assert _schema_of(_body(response_format=response_format)) == {**SCHEMA, "additionalProperties": False}

    def test_the_callers_own_tools_and_choice_are_untouched(self) -> None:
        body = _body(tools=[WEATHER], tool_choice="required", response_format=_format())
        config = body["toolConfig"]
        assert [t["toolSpec"]["name"] for t in config["tools"]] == ["get_weather"]  # type: ignore[index]
        assert config["toolChoice"] == {"any": {}}  # type: ignore[index]

    def test_reasoning_is_kept_beside_it(self) -> None:
        body = _body(reasoning_effort="high", max_tokens=8192, response_format=_format())
        assert body["additionalModelRequestFields"] == {"thinking": {"type": "enabled", "budget_tokens": 4096}}
        assert "toolConfig" not in body
        assert _definition(body)["name"] == "answer"

    def test_a_model_the_catalog_registers_with_the_flag_gets_it(self) -> None:
        model = "custom.model-v1:0"
        assert "outputConfig" not in _body(model, response_format=_format())
        register_model(model, {"supports_native_structured_output": True})
        assert "outputConfig" in _body(model, response_format=_format())

    @pytest.mark.parametrize(
        "response_format",
        [
            {"type": "json_object"},
            {"type": "text"},
            {"type": "json_schema"},
            {"type": "json_schema", "json_schema": {}},
        ],
    )
    def test_a_format_without_a_schema_asks_for_nothing(self, response_format: object) -> None:
        body = _body(response_format=response_format)
        assert "outputConfig" not in body
        assert "toolConfig" not in body


class TestWhichModelsHaveIt:
    @pytest.mark.parametrize(
        "model",
        [
            NATIVE,
            "anthropic.claude-haiku-4-5-20251001-v1:0",
            "us.anthropic.claude-opus-4-5-20251101-v1:0",
            "deepseek.v3-v1:0",
            "qwen.qwen3-235b-a22b-2507-v1:0",
            "mistral.mistral-large-3-675b-instruct",
        ],
    )
    def test_the_models_the_catalog_lists_are_asked_natively(self, model: str) -> None:
        assert "outputConfig" in _body(model, response_format=_format())
        assert "toolConfig" not in _body(model, response_format=_format())

    @pytest.mark.parametrize(
        "model",
        [
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            "amazon.nova-pro-v1:0",
            "us.amazon.nova-2-lite-v1:0",
            "openai.gpt-oss-120b-1:0",
            "meta.llama3-70b-instruct-v1:0",
        ],
    )
    def test_every_other_model_is_asked_through_the_tool(self, model: str) -> None:
        body = _body(model, response_format=_format())
        assert "outputConfig" not in body
        assert body["toolConfig"]["tools"][0]["toolSpec"]["name"] == JSON_TOOL  # type: ignore[index]


class TestClosingTheSchema:
    """Every object the schema describes, wherever it sits, states that it takes no other property."""

    def test_nested_objects_items_and_alternatives_are_closed(self) -> None:
        schema: Body = {
            "type": "object",
            "properties": {
                "child": {"type": "object", "properties": {"n": {"type": "integer"}}},
                "list": {"type": "array", "items": {"type": "object", "properties": {}}},
                "either": {"anyOf": [{"type": "object"}, {"type": "string"}]},
                "all": {"allOf": [{"type": "object"}]},
                "one": {"oneOf": [{"type": "object"}]},
            },
            "$defs": {"D": {"type": "object"}},
            "definitions": {"E": {"type": "object"}},
        }
        closed = _schema_of(_body(response_format=_format(schema)))
        assert closed["additionalProperties"] is False
        props = closed["properties"]
        assert props["child"]["additionalProperties"] is False  # type: ignore[index]
        assert props["list"]["items"]["additionalProperties"] is False  # type: ignore[index]
        assert [p.get("additionalProperties") for p in props["either"]["anyOf"]] == [False, None]  # type: ignore[index]
        assert props["all"]["allOf"][0]["additionalProperties"] is False  # type: ignore[index]
        assert props["one"]["oneOf"][0]["additionalProperties"] is False  # type: ignore[index]
        assert closed["$defs"]["D"]["additionalProperties"] is False  # type: ignore[index]
        assert closed["definitions"]["E"]["additionalProperties"] is False  # type: ignore[index]

    def test_a_boolean_schema_is_left_as_it_is(self) -> None:
        schema: Body = {"type": "object", "properties": {"anything": True, "nothing": False}}
        closed = _schema_of(_body(response_format=_format(schema)))
        assert closed["properties"] == {"anything": True, "nothing": False}
        assert closed["additionalProperties"] is False

    @pytest.mark.parametrize("stated", [True, {"type": "string"}, False])
    def test_a_statement_the_caller_made_stays(self, stated: object) -> None:
        schema = {"type": "object", "properties": {}, "additionalProperties": stated}
        assert _schema_of(_body(response_format=_format(schema)))["additionalProperties"] == stated

    def test_references_stay_references_for_the_api_to_resolve(self) -> None:
        schema = {"type": "object", "properties": {"a": {"$ref": "#/$defs/A"}}, "$defs": {"A": {"type": "object"}}}
        closed = _schema_of(_body(response_format=_format(schema)))
        assert closed["properties"] == {"a": {"$ref": "#/$defs/A"}}
        assert closed["$defs"] == {"A": {"type": "object", "additionalProperties": False}}

    def test_the_callers_schema_is_not_changed(self) -> None:
        schema: Body = {"type": "object", "properties": {"child": {"type": "object"}}}
        before = json.dumps(schema)
        _body(response_format=_format(schema))
        assert json.dumps(schema) == before
