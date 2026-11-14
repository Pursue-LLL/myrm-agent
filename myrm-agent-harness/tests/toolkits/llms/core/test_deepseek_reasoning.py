"""Unit tests for DeepSeek reasoning effort mapping and thinking protocol adapter.

Validates:
1. Model detection: prefix, substring, and host matching; OpenRouter exclusion.
2. Always-on model guard: R1 and deepseek-reasoner strip reasoning_effort and thinking params.
3. Effort mapping: low/high/max passthrough, medium -> high, xhigh -> max for V4-pro/flash.
4. Disabled/off mode: extra_body.thinking={'type': 'disabled'} and parameter stripping.
5. Auto-enabling thinking mode for DeepSeek configurable reasoning models when effort is unspecified.
6. DeepSeek models served by gateways behind the ``openai/`` segment: recognised by bare model id, explicit controls only.
7. End-to-end integration via create_chat_model and LLMManager.
"""

from unittest.mock import MagicMock, patch

from myrm_agent_harness.core.config.llm import LLMConfig
from myrm_agent_harness.toolkits.llms.core.deepseek_reasoning import (
    apply_deepseek_reasoning_effort,
    is_deepseek_always_on_reasoning_model,
    is_deepseek_model,
    is_deepseek_reasoning_model,
    is_hosted_deepseek_reasoning_model,
)
from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model
from myrm_agent_harness.toolkits.llms.core.manager import LLMManager


class TestDeepSeekModelDetection:
    """Tests for is_deepseek_model and reasoning model categorization."""

    def test_direct_deepseek_prefixes(self) -> None:
        assert is_deepseek_model("deepseek/deepseek-v4-pro") is True
        assert is_deepseek_model("deepseek/deepseek-chat") is True
        assert is_deepseek_model("deepseek-r1") is True

    def test_host_based_detection(self) -> None:
        assert is_deepseek_model("custom-model", base_url="https://api.deepseek.com/v1") is True
        assert is_deepseek_model("openai/my-deepseek", base_url="http://api.deepseek.com") is True

    def test_openrouter_excluded(self) -> None:
        """OpenRouter routes through its own protocol, must not be intercepted."""
        assert is_deepseek_model("openrouter/deepseek/deepseek-v4-pro") is False

    def test_non_deepseek_models(self) -> None:
        assert is_deepseek_model("openai/gpt-4o") is False
        assert is_deepseek_model("anthropic/claude-3-opus") is False

    def test_always_on_model_identification(self) -> None:
        assert is_deepseek_always_on_reasoning_model("deepseek/deepseek-r1") is True
        assert is_deepseek_always_on_reasoning_model("deepseek-reasoner") is True
        assert is_deepseek_always_on_reasoning_model("deepseek/deepseek-v4-pro") is False

    def test_reasoning_model_identification(self) -> None:
        assert is_deepseek_reasoning_model("deepseek/deepseek-v4-pro") is True
        assert is_deepseek_reasoning_model("deepseek-v4-flash") is True
        assert is_deepseek_reasoning_model("deepseek-r1") is True
        assert is_deepseek_reasoning_model("deepseek-reasoner") is True
        assert is_deepseek_reasoning_model("deepseek-chat") is False


class TestApplyDeepSeekReasoningEffort:
    """Tests for apply_deepseek_reasoning_effort logic."""

    def test_non_deepseek_noop(self) -> None:
        kwargs = {"reasoning_effort": "high"}
        apply_deepseek_reasoning_effort("openai/gpt-4o", kwargs)
        assert kwargs == {"reasoning_effort": "high"}
        assert "extra_body" not in kwargs

    def test_always_on_r1_strips_effort_and_thinking(self) -> None:
        kwargs = {"reasoning_effort": "high"}
        apply_deepseek_reasoning_effort("deepseek/deepseek-r1", kwargs)
        assert "reasoning_effort" not in kwargs
        assert "reasoning_effort" not in kwargs.get("extra_body", {})
        assert "thinking" not in kwargs.get("extra_body", {})

    def test_always_on_reasoner_strips_off(self) -> None:
        kwargs = {"reasoning_effort": "off"}
        apply_deepseek_reasoning_effort("deepseek-reasoner", kwargs)
        assert "reasoning_effort" not in kwargs
        assert "thinking" not in kwargs.get("extra_body", {})

    def test_explicit_off_disables_thinking_on_v4(self) -> None:
        for val in ("off", "disabled", "none", "0"):
            kwargs = {"reasoning_effort": val}
            apply_deepseek_reasoning_effort("deepseek/deepseek-v4-pro", kwargs)
            assert kwargs.get("extra_body", {}).get("thinking") == {"type": "disabled"}
            assert "reasoning_effort" not in kwargs
            assert "reasoning_effort" not in kwargs["extra_body"]

    def test_native_levels_mapped_on_v4(self) -> None:
        for level in ("low", "high", "max"):
            kwargs = {"reasoning_effort": level}
            apply_deepseek_reasoning_effort("deepseek/deepseek-v4-pro", kwargs)
            assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}
            assert kwargs["extra_body"]["reasoning_effort"] == level
            assert kwargs["reasoning_effort"] == level

    def test_smooth_mappings_medium_and_xhigh(self) -> None:
        # medium -> high
        kwargs_med = {"reasoning_effort": "medium"}
        apply_deepseek_reasoning_effort("deepseek/deepseek-v4-pro", kwargs_med)
        assert kwargs_med["extra_body"]["thinking"] == {"type": "enabled"}
        assert kwargs_med["extra_body"]["reasoning_effort"] == "high"
        assert kwargs_med["reasoning_effort"] == "high"

        # xhigh -> max
        kwargs_xh = {"reasoning_effort": "xhigh"}
        apply_deepseek_reasoning_effort("deepseek/deepseek-v4-pro", kwargs_xh)
        assert kwargs_xh["extra_body"]["thinking"] == {"type": "enabled"}
        assert kwargs_xh["extra_body"]["reasoning_effort"] == "max"
        assert kwargs_xh["reasoning_effort"] == "max"

    def test_auto_enables_thinking_for_v4_when_unspecified(self) -> None:
        """When effort is None on a configurable model, thinking=enabled is auto-injected."""
        kwargs: dict = {}
        apply_deepseek_reasoning_effort("deepseek/deepseek-v4-pro", kwargs)
        assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}
        assert "reasoning_effort" not in kwargs.get("extra_body", {})

    def test_does_not_inject_thinking_for_chat_models_when_unspecified(self) -> None:
        kwargs: dict = {}
        apply_deepseek_reasoning_effort("deepseek/deepseek-chat", kwargs)
        assert "extra_body" not in kwargs or "thinking" not in kwargs.get("extra_body", {})


_GATEWAY = "https://opencode.ai/zen/go/v1"


class TestHostedDeepSeekDetection:
    """DeepSeek models behind another provider's OpenAI-shaped endpoint are recognised by their bare model id."""

    def test_gateway_models_are_recognised(self) -> None:
        assert is_hosted_deepseek_reasoning_model("openai/deepseek-v4.1-flash", _GATEWAY) is True
        assert is_hosted_deepseek_reasoning_model("openai/deepseek-v4-pro", "https://api.siliconflow.cn/v1") is True
        assert is_hosted_deepseek_reasoning_model("openai/deepseek-r1", _GATEWAY) is True
        assert is_hosted_deepseek_reasoning_model("openai/opencode-go-magpie/deepseek-v4.1-flash", _GATEWAY) is True

    def test_other_model_families_are_not_recognised(self) -> None:
        assert is_hosted_deepseek_reasoning_model("openai/gpt-5.6", _GATEWAY) is False
        assert is_hosted_deepseek_reasoning_model("openai/Qwen/Qwen3-32B", _GATEWAY) is False
        assert is_hosted_deepseek_reasoning_model("openai/deepseek-chat", _GATEWAY) is False

    def test_providers_with_their_own_protocol_are_excluded(self) -> None:
        assert is_hosted_deepseek_reasoning_model("deepseek/deepseek-v4-pro") is False
        assert is_hosted_deepseek_reasoning_model("openrouter/deepseek/deepseek-v4-pro") is False

    def test_wires_without_an_openai_body_are_excluded(self) -> None:
        assert is_hosted_deepseek_reasoning_model("anthropic/deepseek-v4-flash") is False

    def test_unresolvable_model_is_not_recognised(self) -> None:
        assert is_hosted_deepseek_reasoning_model("deepseek-v4-flash") is False


class TestApplyHostedDeepSeekReasoningEffort:
    """A gateway-hosted DeepSeek model gets the explicit controls only; nothing is chosen for the caller."""

    @staticmethod
    def _apply(effort: str | None, model: str = "openai/deepseek-v4.1-flash") -> dict:
        kwargs: dict = {"api_base": _GATEWAY}
        if effort is not None:
            kwargs["reasoning_effort"] = effort
        apply_deepseek_reasoning_effort(model, kwargs)
        return kwargs

    def test_unspecified_effort_changes_nothing(self) -> None:
        kwargs = self._apply(None)
        assert "reasoning_effort" not in kwargs
        assert kwargs["extra_body"] == {}

    def test_levels_carry_the_mapped_effort_and_no_thinking_field(self) -> None:
        for raw, mapped in (("low", "low"), ("medium", "high"), ("high", "high"), ("xhigh", "max"), ("max", "max")):
            kwargs = self._apply(raw)
            assert kwargs["reasoning_effort"] == mapped
            assert kwargs["extra_body"] == {"reasoning_effort": mapped}

    def test_off_sends_the_disable_switch_and_no_effort(self) -> None:
        for raw in ("off", "disabled", "none", "0"):
            kwargs = self._apply(raw)
            assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
            assert "reasoning_effort" not in kwargs

    def test_always_on_model_strips_every_control(self) -> None:
        kwargs = self._apply("high", model="openai/deepseek-r1")
        assert "reasoning_effort" not in kwargs
        assert kwargs["extra_body"] == {}

    def test_non_deepseek_gateway_model_is_untouched(self) -> None:
        kwargs = self._apply("max", model="openai/Qwen/Qwen3-32B")
        assert kwargs == {"api_base": _GATEWAY, "reasoning_effort": "max"}


class TestCreateChatModelIntegration:
    """Tests for end-to-end integration via create_chat_model."""

    @patch("myrm_agent_harness.toolkits.llms.core.llm.TransportChatModel")
    def test_deepseek_v4_pro_max_effort(self, mock_cls: MagicMock) -> None:
        create_chat_model("deepseek/deepseek-v4-pro", reasoning_effort="max")
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["extra_body"]["thinking"] == {"type": "enabled"}
        assert call_kwargs["extra_body"]["reasoning_effort"] == "max"
        assert call_kwargs["reasoning_effort"] == "max"

    @patch("myrm_agent_harness.toolkits.llms.core.llm.TransportChatModel")
    def test_deepseek_v4_flash_off_effort(self, mock_cls: MagicMock) -> None:
        create_chat_model("deepseek/deepseek-v4-flash", reasoning_effort="off")
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["extra_body"]["thinking"] == {"type": "disabled"}
        assert "reasoning_effort" not in call_kwargs.get("extra_body", {})

    @patch("myrm_agent_harness.toolkits.llms.core.llm.TransportChatModel")
    def test_deepseek_v4_medium_promoted_to_high(self, mock_cls: MagicMock) -> None:
        create_chat_model("deepseek/deepseek-v4-pro", reasoning_effort="medium")
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["extra_body"]["thinking"] == {"type": "enabled"}
        assert call_kwargs["extra_body"]["reasoning_effort"] == "high"
        assert call_kwargs["reasoning_effort"] == "high"

    @patch("myrm_agent_harness.toolkits.llms.core.llm.TransportChatModel")
    def test_deepseek_r1_always_on_guard_strips_effort(self, mock_cls: MagicMock) -> None:
        create_chat_model("deepseek/deepseek-r1", reasoning_effort="medium")
        call_kwargs = mock_cls.call_args[1]
        assert "reasoning_effort" not in call_kwargs.get("extra_body", {})
        assert "reasoning_effort" not in call_kwargs
        assert "thinking" not in call_kwargs.get("extra_body", {})

    @patch("myrm_agent_harness.toolkits.llms.core.llm.TransportChatModel")
    def test_deepseek_reasoner_always_on_guard_strips_off(self, mock_cls: MagicMock) -> None:
        create_chat_model("deepseek-reasoner", reasoning_effort="off")
        call_kwargs = mock_cls.call_args[1]
        assert "reasoning_effort" not in call_kwargs.get("extra_body", {})
        assert "thinking" not in call_kwargs.get("extra_body", {})


class TestLLMManagerConfigIntegration:
    """Tests for LLMManager.get_llm_from_config reasoning_effort handling."""

    @patch("myrm_agent_harness.toolkits.llms.core.llm.TransportChatModel")
    async def test_top_level_reasoning_effort_precedence(self, mock_cls: MagicMock) -> None:
        LLMManager.clear_cache()
        config = LLMConfig(
            model="deepseek/deepseek-v4-pro",
            api_key="sk-test-key",
            reasoning_effort="max",
            model_kwargs={"reasoning_effort": "low"},
        )
        llm = await LLMManager.get_llm_from_config(config)
        assert llm is not None
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["reasoning_effort"] == "max"
        assert call_kwargs["extra_body"]["reasoning_effort"] == "max"
