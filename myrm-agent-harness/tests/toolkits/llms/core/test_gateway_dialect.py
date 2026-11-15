"""Tests for the thinking switch a gateway documents, applied to the kwargs the model factory builds.

Real hosts are used: the rules key on the endpoint host, so a stand-in URL would test nothing. The wire-level proof that
the switch reaches the gateway is in ``test_gateway_reasoning_wire``.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.core.gateway_dialect import apply_gateway_thinking

_SILICONFLOW = "https://api.siliconflow.cn/v1"
_NVIDIA = "https://integrate.api.nvidia.com/v1"
_QWEN = "openai/Qwen/Qwen3-32B"
_SF_DEEPSEEK = "openai/deepseek-ai/DeepSeek-V4-Flash"
_NV_DEEPSEEK = "openai/deepseek-ai/deepseek-v4-flash"


def _kwargs(base_url: str | None, effort: object = None, **extra_body: object) -> dict[str, object]:
    """The kwargs shape the factory builds: the effort at the top level and mirrored into ``extra_body``."""
    kwargs: dict[str, object] = {}
    if base_url is not None:
        kwargs["api_base"] = base_url
    body = dict(extra_body)
    if effort is not None:
        kwargs["reasoning_effort"] = effort
        body["reasoning_effort"] = effort
    if body:
        kwargs["extra_body"] = body
    return kwargs


def _body(kwargs: dict[str, object]) -> dict[str, object]:
    body = kwargs.get("extra_body")
    assert isinstance(body, dict)
    return body


class TestSiliconFlow:
    def test_off_becomes_the_boolean_switch(self) -> None:
        kwargs = _kwargs(_SILICONFLOW, "off")

        apply_gateway_thinking(_QWEN, kwargs)

        assert _body(kwargs) == {"enable_thinking": False}
        assert "reasoning_effort" not in kwargs

    def test_a_deepseek_disable_object_becomes_the_boolean_switch(self) -> None:
        kwargs = _kwargs(_SILICONFLOW, thinking={"type": "disabled"})
        kwargs["thinking"] = {"type": "disabled"}

        apply_gateway_thinking(_SF_DEEPSEEK, kwargs)

        assert _body(kwargs) == {"enable_thinking": False}
        assert "thinking" not in kwargs

    def test_an_enable_object_becomes_the_boolean_switch(self) -> None:
        kwargs = _kwargs(_SILICONFLOW, thinking={"type": "enabled"})

        apply_gateway_thinking(_QWEN, kwargs)

        assert _body(kwargs) == {"enable_thinking": True}

    @pytest.mark.parametrize("model", [_QWEN, _SF_DEEPSEEK, "openai/zai-org/GLM-5.2"])
    @pytest.mark.parametrize("level", ["low", "high", "max"])
    def test_a_depth_level_is_left_as_it_is(self, model: str, level: str) -> None:
        """No switch is documented for turning thinking on at a depth, and ``low`` is what every lite model gets."""
        kwargs = _kwargs(_SILICONFLOW, level)

        apply_gateway_thinking(model, kwargs)

        assert kwargs == _kwargs(_SILICONFLOW, level)

    def test_the_caller_switch_wins(self) -> None:
        kwargs = _kwargs(_SILICONFLOW, "off", enable_thinking=True)

        apply_gateway_thinking(_QWEN, kwargs)

        assert _body(kwargs)["enable_thinking"] is True

    def test_no_choice_leaves_the_request_untouched(self) -> None:
        kwargs = _kwargs(_SILICONFLOW, keep=True)
        before = {key: dict(value) if isinstance(value, dict) else value for key, value in kwargs.items()}

        apply_gateway_thinking(_QWEN, kwargs)

        assert kwargs == before

    def test_the_callers_extra_body_is_never_edited_in_place(self) -> None:
        shared = {"reasoning_effort": "off", "keep": True}
        kwargs: dict[str, object] = {"api_base": _SILICONFLOW, "reasoning_effort": "off", "extra_body": shared}

        apply_gateway_thinking(_QWEN, kwargs)

        assert shared == {"reasoning_effort": "off", "keep": True}
        assert _body(kwargs) == {"keep": True, "enable_thinking": False}


class TestNvidiaDeepSeekV4:
    def test_off_is_a_chat_template_switch(self) -> None:
        kwargs = _kwargs(_NVIDIA, "off")

        apply_gateway_thinking(_NV_DEEPSEEK, kwargs)

        assert _body(kwargs) == {"chat_template_kwargs": {"thinking": False}}
        assert "reasoning_effort" not in kwargs

    @pytest.mark.parametrize(
        ("level", "documented"),
        [("high", "high"), ("max", "max"), ("xhigh", "max"), ("ultra", "max")],
    )
    def test_a_documented_level_travels_in_the_chat_template(self, level: str, documented: str) -> None:
        kwargs = _kwargs(_NVIDIA, level)

        apply_gateway_thinking(_NV_DEEPSEEK, kwargs)

        assert _body(kwargs) == {"chat_template_kwargs": {"thinking": True, "reasoning_effort": documented}}
        assert "reasoning_effort" not in kwargs

    @pytest.mark.parametrize("level", ["low", "medium", "minimal"])
    def test_a_level_the_gateway_never_defined_sends_nothing(self, level: str) -> None:
        kwargs = _kwargs(_NVIDIA, level)

        apply_gateway_thinking(_NV_DEEPSEEK, kwargs)

        assert _body(kwargs) == {}
        assert "reasoning_effort" not in kwargs

    def test_an_enable_object_without_a_level_turns_thinking_on(self) -> None:
        kwargs = _kwargs(_NVIDIA, thinking={"type": "enabled"})

        apply_gateway_thinking(_NV_DEEPSEEK, kwargs)

        assert _body(kwargs) == {"chat_template_kwargs": {"thinking": True}}

    def test_the_callers_template_keys_win(self) -> None:
        kwargs = _kwargs(_NVIDIA, "off", chat_template_kwargs={"thinking": True, "keep": 1})

        apply_gateway_thinking(_NV_DEEPSEEK, kwargs)

        assert _body(kwargs) == {"chat_template_kwargs": {"thinking": True, "keep": 1}}

    def test_no_choice_leaves_the_request_untouched(self) -> None:
        kwargs = _kwargs(_NVIDIA, keep=True)

        apply_gateway_thinking(_NV_DEEPSEEK, kwargs)

        assert kwargs == _kwargs(_NVIDIA, keep=True)

    @pytest.mark.parametrize("model", ["openai/meta/llama-3.3-70b-instruct", "openai/qwen/qwen3-next-80b-a3b-thinking"])
    def test_other_nvidia_models_keep_the_generic_rules(self, model: str) -> None:
        kwargs = _kwargs(_NVIDIA, "high")

        apply_gateway_thinking(model, kwargs)

        assert kwargs == _kwargs(_NVIDIA, "high")


class TestEverythingElseIsLeftAlone:
    @pytest.mark.parametrize(
        ("model", "base_url"),
        [
            (_QWEN, "https://opencode.ai/zen/go/v1"),
            (_QWEN, None),
            ("deepseek/deepseek-v4-flash", None),
            ("anthropic/claude-sonnet-4-5", "https://api.siliconflow.cn/v1"),
        ],
    )
    @pytest.mark.parametrize("effort", ["off", "high"])
    def test_other_endpoints_and_protocols_keep_their_kwargs(
        self, model: str, base_url: str | None, effort: str
    ) -> None:
        kwargs = _kwargs(base_url, effort)

        apply_gateway_thinking(model, kwargs)

        assert kwargs == _kwargs(base_url, effort)
