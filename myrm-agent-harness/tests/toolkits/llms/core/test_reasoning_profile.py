"""Tests for reasoning_profile SSOT and three-tier intent contract."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model
from myrm_agent_harness.toolkits.llms.core.reasoning_profile import (
    apply_thinking_headroom,
    extract_reasoning_effort,
    get_model_headroom_floor,
    get_model_timeout_floor,
    is_reasoning_explicitly_disabled,
    is_reasoning_explicitly_enabled,
    is_thinking_model,
    strip_untranslated_off_effort,
)


class TestCatalogAndMatching:
    """Test prefix matching, case insensitivity, and catalog baseline timeouts."""

    @pytest.mark.parametrize(
        ("model", "expected_timeout", "expected_headroom"),
        [
            ("openai/o3", 600.0, 16384),
            ("o3-mini", 450.0, 16384),
            ("deepseek/deepseek-r1", 600.0, 16384),
            ("deepseek-reasoner", 600.0, 16384),
            ("minimax/MiniMax-M3", 450.0, 16384),
            ("minimax/MiniMax-M3.1-Flash-Preview", 450.0, 16384),
            ("gemini-2.5-pro", 450.0, 16384),
            ("gemini-3-ultra", 450.0, 16384),
            ("qwq-32b", 450.0, 16384),
            ("nemotron-3-super", 600.0, 16384),
            ("grok-4-fast-reasoning", 450.0, 16384),
            ("kimi-k2-thinking", 450.0, 16384),
            ("step-r1", 450.0, 16384),
            ("claude-opus-4", 450.0, 16384),
        ],
    )
    def test_known_models_baseline(
        self,
        model: str,
        expected_timeout: float,
        expected_headroom: int,
    ) -> None:
        assert get_model_timeout_floor(model) == expected_timeout
        assert get_model_headroom_floor(model) == expected_headroom
        assert is_thinking_model(model) is True

    def test_case_and_provider_prefix_handling(self) -> None:
        assert get_model_timeout_floor("OpenAI/O3") == 600.0
        assert get_model_timeout_floor("DEEPSEEK/DEEPSEEK-R1") == 600.0
        assert get_model_timeout_floor("openrouter/minimax/minimax-m3.1") == 450.0

    def test_non_reasoning_models_return_none(self) -> None:
        for model in ("gpt-4o", "gpt-4o-mini", "llama-3.1-70b", "mistral-large", ""):
            assert get_model_timeout_floor(model) is None
            assert get_model_headroom_floor(model) is None
            assert is_thinking_model(model) is False


class TestThreeTierIntentLadder:
    """Test intent resolution: explicit disabled, explicit enabled, and custom models."""

    def test_explicit_disabled_overrides_catalog(self) -> None:
        kwargs_off: dict[str, object] = {"reasoning_effort": "off"}
        assert is_reasoning_explicitly_disabled(kwargs_off) is True
        assert get_model_timeout_floor("o3", kwargs_off) is None
        assert get_model_headroom_floor("o3", kwargs_off) is None
        assert is_thinking_model("o3", kwargs_off) is False

        kwargs_supports_false: dict[str, object] = {"supports_reasoning": False}
        assert is_reasoning_explicitly_disabled(kwargs_supports_false) is True
        assert get_model_timeout_floor("deepseek-r1", kwargs_supports_false) is None

        kwargs_thinking_disabled: dict[str, object] = {"extra_body": {"thinking": {"type": "disabled"}}}
        assert is_reasoning_explicitly_disabled(kwargs_thinking_disabled) is True
        assert get_model_timeout_floor("deepseek-v4", kwargs_thinking_disabled) is None

    def test_supports_reasoning_toggle_on_custom_model(self) -> None:
        kwargs: dict[str, object] = {"supports_reasoning": True}
        assert is_reasoning_explicitly_enabled(kwargs) is True
        assert get_model_timeout_floor("custom/corp-model", kwargs) == 450.0
        assert get_model_headroom_floor("custom/corp-model", kwargs) == 16384

    def test_supports_reasoning_with_effort_on_custom_model(self) -> None:
        kwargs_high: dict[str, object] = {
            "supports_reasoning": True,
            "reasoning_effort": "high",
        }
        assert is_reasoning_explicitly_enabled(kwargs_high) is True
        assert get_model_timeout_floor("custom/my-fine-tuned-r1", kwargs_high) == 600.0
        assert get_model_headroom_floor("custom/my-fine-tuned-r1", kwargs_high) == 32768
        assert is_thinking_model("custom/my-fine-tuned-r1", kwargs_high) is True

    def test_effort_extraction_order(self) -> None:
        assert extract_reasoning_effort({"reasoning_effort": "HIGH"}) == "high"
        assert extract_reasoning_effort({"extra_body": {"reasoning_effort": "low"}}) == "low"
        assert extract_reasoning_effort({"extra_body": {"reasoning": {"effort": "medium"}}}) == "medium"


class TestApplyThinkingHeadroom:
    """Test max_tokens headroom bounding logic."""

    def test_unset_max_tokens_set_to_floor(self) -> None:
        kwargs: dict[str, object] = {}
        apply_thinking_headroom("minimax/MiniMax-M3.1-Flash-Preview", kwargs)
        assert kwargs["max_tokens"] == 16384

    def test_small_max_tokens_raised(self) -> None:
        kwargs: dict[str, object] = {"max_tokens": 4096, "reasoning_effort": "high"}
        apply_thinking_headroom("o3", kwargs)
        assert kwargs["max_tokens"] == 32768

    def test_large_max_tokens_preserved(self) -> None:
        kwargs: dict[str, object] = {"max_tokens": 65536, "reasoning_effort": "low"}
        apply_thinking_headroom("o3", kwargs)
        assert kwargs["max_tokens"] == 65536

    def test_non_thinking_untouched(self) -> None:
        kwargs: dict[str, object] = {"max_tokens": 2048}
        apply_thinking_headroom("gpt-4o", kwargs)
        assert kwargs["max_tokens"] == 2048


class TestStripUntranslatedOffEffort:
    """``off`` is not a wire value: a gateway never accepts ``reasoning_effort: off``."""

    @pytest.mark.parametrize("value", ["off", "OFF", " disabled ", "false", "0"])
    def test_off_values_leave_both_levels(self, value: str) -> None:
        kwargs: dict[str, object] = {"reasoning_effort": value, "extra_body": {"reasoning_effort": value, "keep": 1}}
        strip_untranslated_off_effort(kwargs)
        assert "reasoning_effort" not in kwargs
        assert kwargs["extra_body"] == {"keep": 1}

    @pytest.mark.parametrize("value", ["low", "medium", "high", "xhigh", "max"])
    def test_wire_levels_are_kept(self, value: str) -> None:
        kwargs: dict[str, object] = {"reasoning_effort": value, "extra_body": {"reasoning_effort": value}}
        strip_untranslated_off_effort(kwargs)
        assert kwargs == {"reasoning_effort": value, "extra_body": {"reasoning_effort": value}}

    def test_without_an_effort_nothing_changes(self) -> None:
        kwargs: dict[str, object] = {"temperature": 0.2}
        strip_untranslated_off_effort(kwargs)
        assert kwargs == {"temperature": 0.2}


class TestLocalEndpointConvergence:
    """Test convergence of local endpoint stall relaxation and reasoning timeout."""

    def test_local_reasoning_model_behavior(self) -> None:
        llm = create_chat_model(
            "qwq-32b",
            api_key="sk-test",
            base_url="http://127.0.0.1:11434",
        )
        assert llm.request_timeout == 1800.0  # max(reasoning 450, local 1800)
        assert llm.first_event_timeout == 300.0  # max(reasoning 225, local 300)
        assert llm.inter_chunk_timeout == 600.0  # local inter_chunk relaxation

    def test_user_explicit_override_takes_precedence(self) -> None:
        llm = create_chat_model(
            "minimax/MiniMax-M3.1-Flash-Preview",
            api_key="sk-test",
            request_timeout=90.0,
            first_event_timeout=45.0,
        )
        assert llm.request_timeout == 90.0
        assert llm.first_event_timeout == 45.0
