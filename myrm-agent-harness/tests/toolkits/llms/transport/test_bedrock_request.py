"""Bedrock Converse request: endpoint and region, credential, generation parameters and how each model family reasons.

The golden request test pins what the previous client library sent for the same calls; these tests pin the rules
behind it, in particular the ones the golden cases cannot see: regions, environment, model generations and replays.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.catalog import store
from myrm_agent_harness.toolkits.llms.transport import bedrock_converse
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route
from myrm_agent_harness.toolkits.llms.transport.retry import DEFAULT_RETRIES

Message = dict[str, object]
CLAUDE = "anthropic.claude-3-5-sonnet-20241022-v2:0"
# Dated ids the catalog does not list, so the rules under test come from the model name alone: a model that takes a
# token budget, an adaptive one, and the newest generation (which accepts no sampling at all).
BUDGETED = "us.anthropic.claude-sonnet-4-5-20991231-v1:0"
ADAPTIVE = "us.anthropic.claude-sonnet-4-6-20991231-v1:0"
NEWEST = "us.anthropic.claude-opus-4-7-20991231-v1:0"
NOVA = "amazon.nova-pro-v1:0"
NOVA_2 = "amazon.nova-2-lite-v1:0"
GPT_OSS = "openai.gpt-oss-120b-1:0"
SAMPLING = {"temperature": 0.2, "top_p": 0.9, "top_k": 40}
APPLICATION_PROFILE = "arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/abc123"
PROVISIONED = "arn:aws:bedrock:us-east-1:123456789012:provisioned-model/abc123"
IMPORTED = "arn:aws:bedrock:us-east-1:123456789012:imported-model/abc123"
GOV_PROFILE = "arn:aws-us-gov:bedrock:us-gov-west-1:123456789012:application-inference-profile/abc123"
_ENV = ("AWS_REGION_NAME", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_BEARER_TOKEN_BEDROCK")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(store, "_REGISTERED", {})


def _request(
    model: str = CLAUDE,
    messages: list[Message] | None = None,
    *,
    key: str | None = "k",
    base: str | None = None,
    **params: object,
) -> PreparedRequest:
    route = resolve_route(f"bedrock/{model}", api_key=key, api_base=base)
    history = messages if messages is not None else [{"role": "user", "content": "hi"}]
    return bedrock_converse.prepare(route, history, params)


def _body(model: str = CLAUDE, messages: list[Message] | None = None, **params: object) -> dict[str, object]:
    return _request(model, messages, **params).body


def _fields(model: str, **params: object) -> dict[str, object]:
    fields = _body(model, **params).get("additionalModelRequestFields", {})
    assert isinstance(fields, dict)
    return fields


def _tool_turn() -> list[Message]:
    call = {"id": "c1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}
    return [
        {"role": "user", "content": "weather?"},
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "c1", "content": "sunny"},
    ]


class TestEndpoint:
    def test_the_default_endpoint_is_the_regional_runtime_with_the_model_in_the_path(self) -> None:
        assert _request().url == (
            "https://bedrock-runtime.us-west-2.amazonaws.com/model/anthropic.claude-3-5-sonnet-20241022-v2%3A0/converse"
        )

    def test_a_streamed_call_uses_the_stream_operation_and_the_event_stream_framing(self) -> None:
        request = _request(stream=True)
        assert request.url.endswith("/converse-stream")
        assert (request.stream, request.framing) == (True, "eventstream")
        assert (_request().stream, _request().framing) == (False, "eventstream")

    @pytest.mark.parametrize(
        ("env", "region"),
        [
            (
                {"AWS_REGION_NAME": "eu-west-1", "AWS_REGION": "ap-south-1", "AWS_DEFAULT_REGION": "ca-central-1"},
                "eu-west-1",
            ),
            ({"AWS_REGION": "ap-south-1", "AWS_DEFAULT_REGION": "ca-central-1"}, "ap-south-1"),
            ({"AWS_DEFAULT_REGION": "ca-central-1"}, "ca-central-1"),
            ({}, "us-west-2"),
        ],
    )
    def test_the_region_comes_from_the_first_variable_set(
        self, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], region: str
    ) -> None:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        assert _request().url.startswith(f"https://bedrock-runtime.{region}.amazonaws.com/model/")

    def test_a_model_arn_names_its_own_region_and_is_escaped_whole(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        arn = "arn:aws:bedrock:us-east-2:123456789012:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        url = _request(arn).url
        assert url.startswith(
            "https://bedrock-runtime.us-east-2.amazonaws.com/model/arn%3Aaws%3Abedrock%3Aus-east-2%3A"
        )
        assert "%2Fus.anthropic.claude-3-5-sonnet-20241022-v2%3A0/converse" in url

    def test_an_arn_of_another_partition_names_its_region_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        assert _request(GOV_PROFILE).url.startswith("https://bedrock-runtime.us-gov-west-1.amazonaws.com/model/")

    @pytest.mark.parametrize("model", ["converse/" + CLAUDE, "invoke/" + CLAUDE])
    def test_the_operation_prefix_of_a_route_is_not_part_of_the_model_id(self, model: str) -> None:
        assert _request(model).url == _request(CLAUDE).url

    def test_the_prefix_leaves_the_arn_region_and_the_catalog_lookup_working(self) -> None:
        arn = "arn:aws:bedrock:us-east-2:123456789012:inference-profile/us.amazon.nova-pro-v1:0"
        request = _request(
            "converse/" + arn, tools=[{"type": "function", "function": {"name": "t"}}], tool_choice="any"
        )
        assert request.url.startswith("https://bedrock-runtime.us-east-2.amazonaws.com/model/arn%3Aaws%3A")
        assert request.body["toolConfig"]["toolChoice"] == {"any": {}}  # type: ignore[index]

    def test_a_custom_endpoint_replaces_the_default_and_a_pasted_operation_url_is_cut_back(self) -> None:
        assert _request(base="https://gw.example/").url.startswith("https://gw.example/model/")
        assert _request(base="https://gw.example/model/x/converse").url.startswith("https://gw.example/model/anthropic")

    def test_a_region_placeholder_in_a_custom_endpoint_is_filled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_REGION_NAME", "eu-central-1")
        url = _request(base="https://vpce.{region}.example.com").url
        assert url.startswith("https://vpce.eu-central-1.example.com/model/")


class TestCredentialAndTransportOptions:
    def test_the_key_is_sent_as_a_bearer_token(self) -> None:
        assert _request(key="secret").headers == {"Authorization": "Bearer secret"}

    def test_the_environment_key_is_the_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "from-env")
        assert _request(key=None).headers["Authorization"] == "Bearer from-env"

    def test_caller_headers_are_added_and_override_case_insensitively(self) -> None:
        headers = _request(extra_headers={"x-trace": "1", "authorization": "Bearer other"}).headers
        assert headers == {"x-trace": "1", "authorization": "Bearer other"}

    def test_timeout_proxy_and_retries_are_carried(self) -> None:
        request = _request(timeout=12, proxy="http://proxy:3128")
        assert (request.timeout, request.proxy, request.retries) == (12.0, "http://proxy:3128", DEFAULT_RETRIES)
        assert request.provider == "bedrock"


class TestMessagesAndSystem:
    def test_messages_and_system_are_the_converse_turns(self) -> None:
        body = _body(messages=[{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}])
        assert body["system"] == [{"text": "Be brief."}]
        assert body["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]

    def test_no_system_prompt_means_no_system_field(self) -> None:
        assert "system" not in _body()

    def test_the_inference_config_is_always_present(self) -> None:
        assert _body()["inferenceConfig"] == {}


class TestInferenceConfig:
    def test_the_answer_budget_is_the_completion_limit_when_both_are_given(self) -> None:
        assert _body(max_tokens=100, max_completion_tokens=200)["inferenceConfig"] == {"maxTokens": 200}

    @pytest.mark.parametrize("limit", [0, -5, True, "100", 1.5])
    def test_a_limit_that_is_not_a_positive_integer_is_ignored(self, limit: object) -> None:
        assert _body(max_tokens=limit)["inferenceConfig"] == {}

    def test_a_model_without_the_claude_restriction_takes_temperature_and_top_p_together(self) -> None:
        assert _body(NOVA, **SAMPLING)["inferenceConfig"] == {"temperature": 0.2, "topP": 0.9}

    def test_claude_takes_temperature_over_top_p_because_the_api_refuses_both(self) -> None:
        assert _body(CLAUDE, **SAMPLING)["inferenceConfig"] == {"temperature": 0.2}

    def test_claude_takes_top_p_alone(self) -> None:
        assert _body(CLAUDE, top_p=0.9)["inferenceConfig"] == {"topP": 0.9}

    def test_top_k_rides_in_the_model_fields_where_the_model_takes_one(self) -> None:
        assert _fields(CLAUDE, top_k=40) == {"top_k": 40}
        assert _fields(NOVA, top_k=40) == {"inferenceConfig": {"topK": 40}}
        assert _fields("us.amazon.nova-lite-v1:0", top_k=5) == {"inferenceConfig": {"topK": 5}}
        # "innovation" contains "nova" and is no Nova.
        for model in ("meta.llama3-70b-instruct-v1:0", "mistral.mistral-large-2402-v1:0", "acme.innovation-v1:0"):
            assert "additionalModelRequestFields" not in _body(model, top_k=40)

    @pytest.mark.parametrize("top_k", [True, 4.5, "40", None])
    def test_top_k_is_a_count(self, top_k: object) -> None:
        assert "additionalModelRequestFields" not in _body(NOVA, top_k=top_k)
        assert "additionalModelRequestFields" not in _body(CLAUDE, top_k=top_k)

    def test_the_newest_generation_gets_no_sampling_at_all(self) -> None:
        body = _body(NEWEST, **SAMPLING)
        assert body["inferenceConfig"] == {}
        assert "additionalModelRequestFields" not in body

    def test_extended_thinking_takes_no_explicit_sampling(self) -> None:
        body = _body(BUDGETED, reasoning_effort="high", **SAMPLING)
        assert body["inferenceConfig"] == {}
        assert "top_k" not in body["additionalModelRequestFields"]  # type: ignore[operator]

    @pytest.mark.parametrize(
        ("stop", "sequences"),
        [("END", ["END"]), (["a", "", "b", 5], ["a", "b"]), ([], None), ("", None), (None, None), (5, None)],
    )
    def test_stop_sequences_are_the_non_empty_strings(self, stop: object, sequences: list[str] | None) -> None:
        config = _body(stop=stop)["inferenceConfig"]
        assert config.get("stopSequences") == sequences  # type: ignore[union-attr]


class TestClaudeThinking:
    def test_a_model_with_a_token_budget_thinks_by_budget(self) -> None:
        assert _fields(BUDGETED, reasoning_effort="high", max_tokens=9000) == {
            "thinking": {"type": "enabled", "budget_tokens": 4096}
        }

    def test_an_adaptive_model_thinks_adaptively_steered_by_effort(self) -> None:
        assert _fields(ADAPTIVE, reasoning_effort="high", max_tokens=9000) == {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
        }

    @pytest.mark.parametrize(
        ("model", "asked", "sent"),
        [(NEWEST, "xhigh", "xhigh"), (NEWEST, "max", "max"), (ADAPTIVE, "xhigh", "max"), (ADAPTIVE, "minimal", "low")],
    )
    def test_the_effort_is_clamped_to_what_the_model_offers(self, model: str, asked: str, sent: str) -> None:
        assert _fields(model, reasoning_effort=asked)["output_config"] == {"effort": sent}

    @pytest.mark.parametrize("effort", ["none", "off", "disabled"])
    def test_a_disabled_effort_sends_no_thinking_and_keeps_sampling(self, effort: str) -> None:
        body = _body(BUDGETED, reasoning_effort=effort, temperature=0.2)
        assert "additionalModelRequestFields" not in body
        assert body["inferenceConfig"] == {"temperature": 0.2}

    def test_thinking_is_off_when_an_earlier_tool_call_lacks_its_signed_block(self) -> None:
        body = _body(BUDGETED, _tool_turn(), reasoning_effort="high", temperature=0.2)
        assert "additionalModelRequestFields" not in body
        assert body["inferenceConfig"] == {"temperature": 0.2}

    def test_an_adaptive_model_keeps_its_effort_when_the_replay_forces_thinking_off(self) -> None:
        body = _body(ADAPTIVE, _tool_turn(), reasoning_effort="high", temperature=0.2)
        assert body["additionalModelRequestFields"] == {"output_config": {"effort": "high"}}
        assert body["inferenceConfig"] == {"temperature": 0.2}

    def test_a_signed_thinking_block_in_the_replay_keeps_thinking_on_and_leads_its_turn(self) -> None:
        messages = _tool_turn()
        messages[1]["thinking_blocks"] = [{"type": "thinking", "thinking": "hmm", "signature": "sig"}]
        body = _body(BUDGETED, messages, reasoning_effort="high")
        assert body["additionalModelRequestFields"] == {"thinking": {"type": "enabled", "budget_tokens": 4096}}
        first = body["messages"][1]["content"][0]  # type: ignore[index]
        assert first == {"reasoningContent": {"reasoningText": {"text": "hmm", "signature": "sig"}}}

    def test_an_explicit_thinking_block_is_sent_as_given_and_takes_no_sampling(self) -> None:
        explicit = {"type": "enabled", "budget_tokens": 2500}
        body = _body(BUDGETED, thinking=explicit, **SAMPLING)
        assert body["additionalModelRequestFields"] == {"thinking": explicit}
        assert body["inferenceConfig"] == {}

    def test_explicitly_disabled_thinking_leaves_sampling_alone(self) -> None:
        body = _body(BUDGETED, thinking={"type": "disabled"}, **SAMPLING)
        assert body["additionalModelRequestFields"] == {"thinking": {"type": "disabled"}, "top_k": 40}
        assert body["inferenceConfig"] == {"temperature": 0.2}


class TestOtherFamiliesReasoning:
    @pytest.mark.parametrize("effort", ["low", "medium", "high", "HIGH"])
    def test_nova_2_takes_a_reasoning_config(self, effort: str) -> None:
        assert _fields(NOVA_2, reasoning_effort=effort) == {
            "reasoningConfig": {"type": "enabled", "maxReasoningEffort": effort.lower()}
        }

    @pytest.mark.parametrize(
        "model",
        [NOVA, "meta.llama3-70b-instruct-v1:0", "mistral.mistral-large-2402-v1:0", "acme.supernova-2-large-v1:0"],
    )
    def test_a_model_without_a_reasoning_switch_gets_none(self, model: str) -> None:
        assert _fields(model, reasoning_effort="high") == {}

    @pytest.mark.parametrize("effort", ["xhigh", "minimal", "none", 5])
    def test_an_effort_the_family_does_not_know_is_not_sent(self, effort: object) -> None:
        assert _fields(NOVA_2, reasoning_effort=effort) == {}
        assert _fields(GPT_OSS, reasoning_effort=effort) == {}

    def test_gpt_oss_takes_the_effort_as_its_own_field(self) -> None:
        assert _fields(GPT_OSS, reasoning_effort="low") == {"reasoning_effort": "low"}

    def test_the_callers_extra_body_goes_into_the_model_fields_and_wins(self) -> None:
        fields = _fields(BUDGETED, reasoning_effort="high", extra_body={"thinking": {"type": "disabled"}, "x": 1})
        assert fields == {"thinking": {"type": "disabled"}, "x": 1}

    def test_extra_body_alone_is_enough_to_create_the_model_fields(self) -> None:
        assert _fields(NOVA, extra_body={"inferenceConfig_extra": True}) == {"inferenceConfig_extra": True}


class TestOpaqueModelArn:
    """An application inference profile or a provisioned model does not say which model answers. Most are Claude, whose
    rules a wrong guess would silently withhold, while a model that refuses them says so in its error."""

    @pytest.mark.parametrize("arn", [APPLICATION_PROFILE, PROVISIONED, GOV_PROFILE])
    def test_it_is_asked_to_think_like_claude(self, arn: str) -> None:
        assert _fields(arn, reasoning_effort="high", max_tokens=9000) == {
            "thinking": {"type": "enabled", "budget_tokens": 4096}
        }

    @pytest.mark.parametrize("arn", [APPLICATION_PROFILE, PROVISIONED])
    def test_it_takes_one_of_temperature_and_top_p_and_the_top_k_field_like_claude(self, arn: str) -> None:
        assert _body(arn, temperature=0.2, top_p=0.9)["inferenceConfig"] == {"temperature": 0.2}
        assert _fields(arn, top_k=40) == {"top_k": 40}

    def test_beside_thinking_it_takes_no_explicit_sampling(self) -> None:
        body = _body(APPLICATION_PROFILE, reasoning_effort="high", **SAMPLING)
        assert body["inferenceConfig"] == {}
        assert "top_k" not in body["additionalModelRequestFields"]  # type: ignore[operator]

    def test_a_forced_tool_call_beside_a_thinking_block_stays_automatic(self) -> None:
        tool = {"type": "function", "function": {"name": "t"}}
        body = _body(APPLICATION_PROFILE, tools=[tool], tool_choice="required", reasoning_effort="high")
        assert body["toolConfig"]["toolChoice"] == {"auto": {}}  # type: ignore[index]

    def test_an_imported_model_is_no_claude(self) -> None:
        body = _body(IMPORTED, reasoning_effort="high", **SAMPLING)
        assert "additionalModelRequestFields" not in body
        assert body["inferenceConfig"] == {"temperature": 0.2, "topP": 0.9}

    def test_an_arn_that_names_its_model_is_read_as_that_model(self) -> None:
        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.amazon.nova-pro-v1:0"
        body = _body(arn, reasoning_effort="high", **SAMPLING)
        assert body["additionalModelRequestFields"] == {"inferenceConfig": {"topK": 40}}  # Nova's top_k, no thinking
        assert body["inferenceConfig"] == {"temperature": 0.2, "topP": 0.9}
