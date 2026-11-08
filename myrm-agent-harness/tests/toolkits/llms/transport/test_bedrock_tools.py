"""Bedrock Converse tools: specs, tool choice, parallel calls, the placeholder tool, grounding and structured output.

Converse has no ``response_format`` for the models without a native one: a structured answer is the forced call of one
synthetic tool, which the answer side turns back into text. The caller's tools and tool choice reach every model as
stated; only a budgeted thinking block and gpt-oss's reasoning effort are known to refuse a forced call.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.llms.catalog import register_model, store
from myrm_agent_harness.toolkits.llms.transport import bedrock_converse, bedrock_structured
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Message = dict[str, object]
Body = dict[str, object]
CLAUDE = "anthropic.claude-3-5-sonnet-20241022-v2:0"
BUDGETED = "us.anthropic.claude-sonnet-4-5-20991231-v1:0"
ADAPTIVE = "us.anthropic.claude-sonnet-4-6-20991231-v1:0"
NEWEST = "us.anthropic.claude-opus-4-7-20991231-v1:0"
NOVA = "amazon.nova-pro-v1:0"
NOVA_2 = "us.amazon.nova-2-lite-v1:0"
GPT_OSS = "openai.gpt-oss-120b-1:0"
LLAMA = "us.meta.llama3-3-70b-instruct-v1:0"
UNTOOLED = "meta.llama3-70b-instruct-v1:0"
JSON_TOOL = bedrock_structured.JSON_TOOL
WEATHER: Body = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Weather of a city",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    },
}
TIME: Body = {"type": "function", "function": {"name": "get_time", "parameters": {"type": "object"}}}
SCHEMA: Body = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})


def _body(model: str = CLAUDE, messages: list[Message] | None = None, **params: object) -> Body:
    route = resolve_route(f"bedrock/{model}", api_key="k")
    history = messages if messages is not None else [{"role": "user", "content": "hi"}]
    return bedrock_converse.prepare(route, history, params).body


def _config(model: str = CLAUDE, messages: list[Message] | None = None, **params: object) -> Body:
    config = _body(model, messages, **params).get("toolConfig", {})
    assert isinstance(config, dict)
    return config


def _tools(model: str = CLAUDE, **params: object) -> list[Body]:
    tools = _config(model, **params).get("tools", [])
    assert isinstance(tools, list)
    return tools


def _spec(tool: Body) -> Body:
    spec = tool["toolSpec"]
    assert isinstance(spec, dict)
    return spec


def _tool_history() -> list[Message]:
    call = {"id": "c1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}
    return [
        {"role": "user", "content": "weather?"},
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "c1", "content": "sunny"},
    ]


def _function(**fields: object) -> Body:
    return {"type": "function", "function": {"name": "t", **fields}}


class TestToolSpecs:
    def test_a_tool_is_its_name_description_and_json_schema(self) -> None:
        assert _tools(tools=[WEATHER]) == [
            {
                "toolSpec": {
                    "name": "get_weather",
                    "description": "Weather of a city",
                    "inputSchema": {"json": WEATHER["function"]["parameters"]},  # type: ignore[index]
                }
            }
        ]

    @pytest.mark.parametrize("description", [None, "", "  \n ", 0])
    def test_an_undescribed_tool_is_described_by_its_name_because_the_api_rejects_blanks(
        self, description: object
    ) -> None:
        assert _spec(_tools(tools=[_function(description=description)])[0])["description"] == "t"

    def test_references_in_the_schema_are_inlined_because_the_api_resolves_none(self) -> None:
        schema = {"type": "object", "properties": {"p": {"$ref": "#/$defs/P"}}, "$defs": {"P": {"type": "string"}}}
        spec = _spec(_tools(tools=[_function(parameters=schema)])[0])
        assert "$ref" not in json.dumps(spec)
        assert spec["inputSchema"] == {"json": {"type": "object", "properties": {"p": {"type": "string"}}}}

    @pytest.mark.parametrize(
        ("parameters", "root"),
        [
            ({"type": "weird"}, "object"),
            ({"properties": {}}, "object"),
            ({"type": "string"}, "string"),
            ({"type": "array"}, "array"),
            (None, "object"),
        ],
    )
    def test_the_root_of_the_schema_has_a_type_the_api_knows(self, parameters: object, root: str) -> None:
        schema = _spec(_tools(tools=[_function(parameters=parameters)])[0])["inputSchema"]["json"]  # type: ignore[index]
        assert schema["type"] == root

    def test_a_tool_without_parameters_takes_an_empty_object(self) -> None:
        schema = _spec(_tools(tools=[_function()])[0])["inputSchema"]
        assert schema == {"json": {"type": "object", "properties": {}}}

    def test_malformed_tools_are_skipped(self) -> None:
        tools = [WEATHER, "junk", {"type": "function"}, {"type": "function", "function": {"parameters": {}}}, 5]
        assert [_spec(t)["name"] for t in _tools(tools=tools)] == ["get_weather"]

    def test_a_name_outside_the_api_alphabet_is_escaped(self) -> None:
        name = _spec(_tools(tools=[_function(name="web.search")])[0])["name"]
        assert name == "x__web_2e_search"

    def test_a_marked_tool_is_followed_by_a_cache_point(self) -> None:
        marked = {"type": "function", "cache_control": {"type": "ephemeral"}, "function": WEATHER["function"]}
        tools = _tools(tools=[marked, TIME])
        assert [list(t) for t in tools] == [["toolSpec"], ["cachePoint"], ["toolSpec"]]
        assert tools[1] == {"cachePoint": {"type": "default"}}

    def test_a_cache_mark_on_the_function_counts_the_same(self) -> None:
        function = {**WEATHER["function"], "cache_control": {"type": "ephemeral"}}  # type: ignore[dict-item]
        assert [list(t) for t in _tools(tools=[{"type": "function", "function": function}])] == [
            ["toolSpec"],
            ["cachePoint"],
        ]

    def test_without_tools_there_is_no_tool_config(self) -> None:
        assert "toolConfig" not in _body()
        assert "toolConfig" not in _body(tools=[])


class TestToolsAreSentAsStated:
    """The catalog can lag a model's real abilities, and the API refuses a tool a model cannot use in plain words; a
    tool withheld on a guess would instead make an agent fail without a word."""

    @pytest.mark.parametrize(
        "model",
        [
            UNTOOLED,
            "meta.llama3-8b-instruct-v1:0",
            "deepseek.r1-v1:0",
            "amazon.titan-text-premier-v1:0",
            CLAUDE,
            "anthropic.claude-future-v9:0",
            "mistral.mistral-large-2407-v1:0",
            "cohere.command-r-plus-v1:0",
            "meta.llama4-scout-17b-instruct-v1:0",
            "amazon.nova-micro-v1:0",
            LLAMA,
            "eu.amazon.nova-lite-v1:0",
            "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "custom.model-v1:0",
        ],
    )
    def test_every_model_is_offered_the_tools_the_caller_declares(self, model: str) -> None:
        assert [_spec(t)["name"] for t in _tools(model, tools=[WEATHER])] == ["get_weather"]

    @pytest.mark.parametrize(
        "model", [UNTOOLED, "deepseek.r1-v1:0", "amazon.titan-text-premier-v1:0", LLAMA, NOVA, CLAUDE]
    )
    @pytest.mark.parametrize(
        ("choice", "expected"),
        [("auto", {"auto": {}}), ("required", {"any": {}}), ({"name": "get_time"}, {"tool": {"name": "get_time"}})],
    )
    def test_every_model_is_sent_the_tool_choice_as_stated(self, model: str, choice: object, expected: Body) -> None:
        assert _config(model, tools=[WEATHER, TIME], tool_choice=choice)["toolChoice"] == expected

    def test_an_arn_that_does_not_name_its_model_is_offered_them(self) -> None:
        arn = "arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/abc123"
        assert [_spec(t)["name"] for t in _tools(arn, tools=[WEATHER])] == ["get_weather"]

    def test_a_profile_arn_that_names_the_model_is_read_like_the_model(self) -> None:
        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.amazon.nova-pro-v1:0"
        assert _tools(arn, tools=[WEATHER], web_search_options={})[-1] == {"systemTool": {"name": "nova_grounding"}}

    def test_a_history_of_tool_calls_still_gets_the_placeholder_when_no_tools_are_declared(self) -> None:
        tools = _tools(UNTOOLED, messages=_tool_history())
        assert [_spec(t)["name"] for t in tools] == ["dummy_tool"]


class TestToolChoice:
    @pytest.mark.parametrize(
        ("choice", "expected"),
        [
            ("auto", {"auto": {}}),
            ("required", {"any": {}}),
            ("any", {"any": {}}),
            ({"type": "function", "function": {"name": "get_time"}}, {"tool": {"name": "get_time"}}),
            ({"name": "get_time"}, {"tool": {"name": "get_time"}}),
            ({"function": {"name": "web.x"}}, {"tool": {"name": "x__web_2e_x"}}),
        ],
    )
    def test_the_choice_maps_onto_converse(self, choice: object, expected: Body) -> None:
        assert _config(tools=[WEATHER, TIME], tool_choice=choice)["toolChoice"] == expected

    @pytest.mark.parametrize("choice", [None, "weird", 5, {}, {"function": {}}])
    def test_a_choice_that_means_nothing_is_not_sent(self, choice: object) -> None:
        assert "toolChoice" not in _config(tools=[WEATHER], tool_choice=choice)

    def test_extended_thinking_refuses_a_forced_call_so_the_choice_stays_automatic(self) -> None:
        for choice in ("required", {"name": "get_time"}):
            config = _config(BUDGETED, tools=[WEATHER, TIME], tool_choice=choice, reasoning_effort="high")
            assert config["toolChoice"] == {"auto": {}}

    def test_reasoning_that_refuses_a_forced_call_leaves_the_choice_automatic(self) -> None:
        # Claude's thinking and gpt-oss's reasoning effort do; Nova 2's reasoning config takes a forced call.
        for choice in ("required", {"name": "get_time"}):
            for model in (BUDGETED, GPT_OSS):
                config = _config(model, tools=[WEATHER, TIME], tool_choice=choice, reasoning_effort="high")
                assert config["toolChoice"] == {"auto": {}}, model
        forced = _config(NOVA_2, tools=[WEATHER, TIME], tool_choice="required", reasoning_effort="high")
        assert forced["toolChoice"] == {"any": {}}
        named = _config(NOVA_2, tools=[WEATHER, TIME], tool_choice={"name": "get_time"}, reasoning_effort="low")
        assert named["toolChoice"] == {"tool": {"name": "get_time"}}

    @pytest.mark.parametrize("model", [ADAPTIVE, NEWEST])
    def test_adaptive_thinking_is_sent_the_forced_call_as_asked(self, model: str) -> None:
        body = _body(model, tools=[WEATHER], tool_choice="required", reasoning_effort="high")
        assert body["additionalModelRequestFields"]["thinking"] == {"type": "adaptive"}  # type: ignore[index]
        assert body["toolConfig"]["toolChoice"] == {"any": {}}  # type: ignore[index]

    def test_an_effort_the_model_does_not_take_is_no_reasoning_so_the_call_stays_forced(self) -> None:
        for model, effort in ((GPT_OSS, "none"), (NOVA_2, "bogus"), (NOVA, "high")):
            config = _config(model, tools=[WEATHER], tool_choice="required", reasoning_effort=effort)
            assert config["toolChoice"] == {"any": {}}, (model, effort)

    def test_none_withdraws_the_tools_instead_of_sending_a_string_the_api_refuses(self) -> None:
        assert "toolConfig" not in _body(tools=[WEATHER], tool_choice="none")

    def test_a_history_of_tool_calls_needs_a_declared_tool_even_when_none_is_wanted(self) -> None:
        for params in ({}, {"tool_choice": "none", "tools": [WEATHER]}):
            tools = _tools(messages=_tool_history(), **params)
            assert [_spec(t)["name"] for t in tools] == ["dummy_tool"]
            assert "toolChoice" not in _config(messages=_tool_history(), **params)

    def test_the_placeholder_is_a_described_tool_without_arguments_whose_schema_lists_none_required(self) -> None:
        assert _spec(_tools(messages=_tool_history())[0]) == {
            "name": "dummy_tool",
            "description": "This is a dummy tool call",
            "inputSchema": {"json": {"type": "object", "properties": {}, "required": []}},
        }

    def test_the_placeholder_is_not_added_when_tools_are_declared(self) -> None:
        assert [_spec(t)["name"] for t in _tools(messages=_tool_history(), tools=[WEATHER])] == ["get_weather"]


class TestParallelToolUse:
    """``parallel_tool_calls`` is Anthropic's ``disable_parallel_tool_use`` for the models the catalog lists for it."""

    LISTED = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    @staticmethod
    def _fields(model: str, **params: object) -> Body:
        fields = _body(model, **params).get("additionalModelRequestFields", {})
        assert isinstance(fields, dict)
        return fields

    @pytest.mark.parametrize(("parallel", "disabled"), [(False, True), (True, False)])
    def test_a_listed_model_is_told_whether_to_call_tools_in_parallel(self, parallel: bool, disabled: bool) -> None:
        fields = self._fields(self.LISTED, tools=[WEATHER], tool_choice="auto", parallel_tool_calls=parallel)
        assert fields == {"tool_choice": {"disable_parallel_tool_use": disabled}}

    def test_without_a_choice_of_its_own_the_request_names_the_automatic_one_beside_it(self) -> None:
        fields = self._fields(self.LISTED, tools=[WEATHER], parallel_tool_calls=False)
        assert fields == {"tool_choice": {"type": "auto", "disable_parallel_tool_use": True}}

    def test_a_choice_without_tools_sends_no_tool_config_so_the_fields_keep_their_type(self) -> None:
        body = _body(self.LISTED, tool_choice="auto", parallel_tool_calls=False)
        assert "toolConfig" not in body
        assert body["additionalModelRequestFields"] == {  # type: ignore[comparison-overlap]
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True}
        }

    def test_a_tool_choice_in_the_request_leaves_no_second_type_in_the_fields(self) -> None:
        # Converse refuses a toolConfig.toolChoice together with additionalModelRequestFields.tool_choice.type.
        extra = {"tool_choice": {"type": "tool", "name": "get_time", "disable_parallel_tool_use": False}}
        fields = self._fields(
            self.LISTED, tools=[WEATHER, TIME], tool_choice="required", parallel_tool_calls=False, extra_body=extra
        )
        assert fields["tool_choice"] == {"name": "get_time", "disable_parallel_tool_use": True}

    def test_a_tool_choice_of_the_callers_extra_body_keeps_its_other_keys_but_not_its_parallel_flag(self) -> None:
        extra = {"tool_choice": {"type": "any", "disable_parallel_tool_use": False}}
        fields = self._fields(self.LISTED, tools=[WEATHER], parallel_tool_calls=False, extra_body=extra)
        assert fields["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}

    @pytest.mark.parametrize("model", [CLAUDE, NOVA, LLAMA, "custom.model-v1:0"])
    def test_a_model_the_catalog_does_not_list_gets_no_such_field(self, model: str) -> None:
        assert "additionalModelRequestFields" not in _body(model, tools=[WEATHER], parallel_tool_calls=False)

    @pytest.mark.parametrize("parallel", [None, "false", 0, 1])
    def test_a_value_that_is_no_boolean_is_not_sent(self, parallel: object) -> None:
        assert "additionalModelRequestFields" not in _body(self.LISTED, tools=[WEATHER], parallel_tool_calls=parallel)

    def test_a_cross_region_id_and_a_profile_arn_are_read_like_the_model_they_name(self) -> None:
        arn = f"arn:aws:bedrock:us-east-1:123456789012:inference-profile/{self.LISTED}"
        for model in (self.LISTED, f"global.{self.LISTED.removeprefix('us.')}", arn):
            fields = self._fields(model, tools=[WEATHER], tool_choice="auto", parallel_tool_calls=False)
            assert fields == {"tool_choice": {"disable_parallel_tool_use": True}}, model

    def test_an_id_with_a_region_prefix_the_catalog_lacks_is_read_by_its_base_model(self) -> None:
        register_model("anthropic.claude-test-v9:0", {"supports_parallel_tool_use_config": True})
        fields = self._fields(
            "eu.anthropic.claude-test-v9:0", tools=[WEATHER], tool_choice="auto", parallel_tool_calls=True
        )
        assert fields == {"tool_choice": {"disable_parallel_tool_use": False}}

    def test_an_id_the_catalog_lists_under_its_region_prefix_alone_is_read_by_that_id(self) -> None:
        register_model("us.anthropic.claude-test-v9:0", {"supports_parallel_tool_use_config": True})
        fields = self._fields(
            "us.anthropic.claude-test-v9:0", tools=[WEATHER], tool_choice="auto", parallel_tool_calls=False
        )
        assert fields == {"tool_choice": {"disable_parallel_tool_use": True}}


class TestGrounding:
    def test_nova_grounding_is_a_system_tool_after_the_callers_tools(self) -> None:
        tools = _tools(NOVA, tools=[WEATHER], web_search_options={})
        assert tools[-1] == {"systemTool": {"name": "nova_grounding"}}
        assert len(tools) == 2

    def test_other_models_do_not_get_it(self) -> None:
        assert "toolConfig" not in _body(CLAUDE, web_search_options={})
        assert "toolConfig" not in _body(NOVA, web_search_options=True)


class TestStructuredOutput:
    @staticmethod
    def _format(schema: Body | None = None, **fields: object) -> Body:
        return {"type": "json_schema", "json_schema": {"name": "r", "schema": schema or SCHEMA, **fields}}

    def test_the_schema_becomes_a_tool_whose_call_is_forced(self) -> None:
        config = _config(response_format=self._format(description="The result"))
        assert config["tools"] == [
            {"toolSpec": {"name": JSON_TOOL, "description": "The result", "inputSchema": {"json": SCHEMA}}}
        ]
        assert config["toolChoice"] == {"tool": {"name": JSON_TOOL}}

    @pytest.mark.parametrize("description", [None, "", "  "])
    def test_an_undescribed_schema_is_described_by_the_tool_name(self, description: object) -> None:
        assert _spec(_tools(response_format=self._format(description=description))[0])["description"] == JSON_TOOL

    def test_the_schema_has_its_references_inlined_like_any_tool(self) -> None:
        schema = {"type": "object", "properties": {"a": {"$ref": "#/$defs/A"}}, "$defs": {"A": {"type": "string"}}}
        assert "$ref" not in json.dumps(_tools(response_format=self._format(schema)))

    @pytest.mark.parametrize("model", [BUDGETED, NOVA_2, GPT_OSS])
    def test_a_model_that_reasons_is_offered_the_tool_not_forced_to_call_it(self, model: str) -> None:
        # With the Anthropic and gpt-oss models the API refuses a forced call; Nova 2 is treated alike so a
        # structured answer never turns on whether a model happens to take one.
        config = _config(model, response_format=self._format(), reasoning_effort="high")
        assert "toolChoice" not in config
        assert _spec(config["tools"][0])["name"] == JSON_TOOL  # type: ignore[index]

    @pytest.mark.parametrize("model", [ADAPTIVE, NEWEST])
    def test_an_adaptive_model_is_offered_the_tool_not_forced_to_call_it(self, model: str) -> None:
        config = _config(model, response_format=self._format(), reasoning_effort="high")
        assert "toolChoice" not in config
        assert _spec(config["tools"][0])["name"] == JSON_TOOL  # type: ignore[index]

    def test_a_reasoning_effort_the_model_does_not_take_leaves_the_call_forced(self) -> None:
        config = _config(NOVA, response_format=self._format(), reasoning_effort="high")
        assert config["toolChoice"] == {"tool": {"name": JSON_TOOL}}

    def test_a_model_not_known_to_take_a_forced_call_is_offered_the_tool_unforced(self) -> None:
        config = _config(LLAMA, response_format=self._format())
        assert "toolChoice" not in config
        assert _spec(config["tools"][0])["name"] == JSON_TOOL  # type: ignore[index]

    def test_a_claude_the_catalog_does_not_list_is_forced_to_call_the_tool_too(self) -> None:
        unlisted = "us.anthropic.claude-sonnet-9-20991231-v1:0"
        assert _config(unlisted, response_format=self._format())["toolChoice"] == {"tool": {"name": JSON_TOOL}}

    def test_a_forced_call_goes_to_claude_and_to_the_models_the_catalog_lists_for_it(self) -> None:
        forced = {"tool": {"name": JSON_TOOL}}
        assert _config(CLAUDE, response_format=self._format())["toolChoice"] == forced
        assert _config(NOVA, response_format=self._format())["toolChoice"] == forced
        assert "toolChoice" not in _config("custom.model-v1:0", response_format=self._format())
        register_model("custom.model-v1:0", {"supports_function_calling": True, "supports_tool_choice": True})
        assert _config("custom.model-v1:0", response_format=self._format())["toolChoice"] == forced

    def test_the_callers_tools_follow_the_structured_tool_and_without_a_choice_of_theirs_it_is_forced(self) -> None:
        config = _config(tools=[WEATHER], response_format=self._format())
        assert [_spec(t)["name"] for t in config["tools"]] == [JSON_TOOL, "get_weather"]  # type: ignore[attr-defined]
        assert config["toolChoice"] == {"tool": {"name": JSON_TOOL}}

    @pytest.mark.parametrize(("choice", "expected"), [("auto", {"auto": {}}), ("required", {"any": {}})])
    def test_a_choice_the_caller_states_wins_over_the_forced_call(self, choice: str, expected: Body) -> None:
        config = _config(tools=[WEATHER], tool_choice=choice, response_format=self._format())
        assert [_spec(t)["name"] for t in config["tools"]] == [JSON_TOOL, "get_weather"]  # type: ignore[attr-defined]
        assert config["toolChoice"] == expected

    def test_the_flat_schema_form_is_read_too(self) -> None:
        config = _config(response_format={"type": "json_schema", "response_schema": SCHEMA})
        assert _spec(config["tools"][0])["inputSchema"] == {"json": SCHEMA}  # type: ignore[index]

    @pytest.mark.parametrize(
        "response_format",
        [
            {"type": "json_object", "json_schema": {"name": "r", "schema": SCHEMA}},
            {"type": "json_object", "response_schema": SCHEMA},
        ],
        ids=["holder", "flat"],
    )
    def test_a_json_object_format_that_carries_a_schema_is_read_like_a_json_schema(self, response_format: Body) -> None:
        config = _config(response_format=response_format)
        assert _spec(config["tools"][0])["inputSchema"] == {"json": SCHEMA}  # type: ignore[index]
        assert config["toolChoice"] == {"tool": {"name": JSON_TOOL}}

    @pytest.mark.parametrize(
        "response_format",
        [
            {"type": "json_object"},
            {"type": "text"},
            {"type": "json_schema"},
            {"type": "json_schema", "json_schema": {"name": "r"}},
            {"type": "json_schema", "json_schema": {"name": "r", "schema": "not a schema"}},
            "json",
        ],
    )
    def test_any_other_response_format_adds_no_tool(self, response_format: object) -> None:
        assert "toolConfig" not in _body(response_format=response_format)
