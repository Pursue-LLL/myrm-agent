"""Model capabilities that shape a request: the catalog states them, the model name covers what it does not."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.catalog import model_facts, register_model, store
from myrm_agent_harness.toolkits.llms.transport.capabilities import (
    ClaudeTraits,
    claude_traits,
    gemini_from_3,
    gemini_thinking_level,
    gemini_thinks_by_level,
    keeps_temperature_without_reasoning,
)


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})


LEGACY = ClaudeTraits()
ADAPTIVE = ClaudeTraits(sampling=True, adaptive_thinking=True, xhigh_effort=False, max_effort=True)
NEWEST = ClaudeTraits(sampling=False, adaptive_thinking=True, xhigh_effort=True, max_effort=True)


class TestClaudeByName:
    """Ids the catalog does not list (a release newer than the snapshot, a dated alias) are classified by name."""

    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("claude-3-5-sonnet-20991231", LEGACY),  # Claude 3 puts the family after the version
            ("claude-opus-4-20991231", LEGACY),  # a snapshot date is not a minor version
            ("claude-opus-4-3", LEGACY),
            ("claude-sonnet-4-4", LEGACY),
            ("claude-opus-4-6-20991231", ADAPTIVE),
            ("claude-sonnet-4-6@vertex", ADAPTIVE),
            ("claude-opus-4-7-20991231", NEWEST),
            ("claude-haiku-5-4-20991231", ClaudeTraits(sampling=False)),
            ("claude-haiku-5-5-20991231", NEWEST),
            ("claude-opus-9-3", NEWEST),
            ("claude-fable-9", NEWEST),
            ("claude-mythos-9", NEWEST),
            ("gpt-4o-2099", LEGACY),
        ],
    )
    def test_traits_follow_the_generation(self, model: str, expected: ClaudeTraits) -> None:
        assert model_facts(model, "anthropic") is None, "the id must be one the catalog does not list"
        assert claude_traits(model) == expected


class TestClaudeByCatalog:
    def test_a_stated_flag_beats_the_name(self) -> None:
        register_model(
            "claude-opus-9-3",
            {
                "provider": "anthropic",
                "supports_sampling_params": True,
                "supports_adaptive_thinking": False,
                "supports_xhigh_reasoning_effort": False,
                "supports_max_reasoning_effort": False,
            },
        )
        assert claude_traits("claude-opus-9-3") == LEGACY

    def test_a_flag_the_entry_does_not_state_falls_back_to_the_name(self) -> None:
        register_model("claude-opus-9-3", {"provider": "anthropic", "supports_sampling_params": True})
        assert claude_traits("claude-opus-9-3") == ClaudeTraits(
            sampling=True, adaptive_thinking=True, xhigh_effort=True, max_effort=True
        )

    def test_the_output_ceiling_comes_from_the_entry(self) -> None:
        register_model("claude-opus-9-3", {"provider": "anthropic", "max_output_tokens": 1234, "max_tokens": 99})
        assert claude_traits("claude-opus-9-3").max_output_tokens == 1234

    def test_the_older_max_tokens_field_is_the_ceiling_when_no_output_limit_is_stated(self) -> None:
        register_model("claude-opus-9-3", {"provider": "anthropic", "max_tokens": 99})
        assert claude_traits("claude-opus-9-3").max_output_tokens == 99

    def test_an_unlisted_model_has_no_ceiling(self) -> None:
        assert claude_traits("claude-opus-9-3").max_output_tokens is None

    def test_the_bundled_snapshot_states_what_each_generation_takes(self) -> None:
        assert claude_traits("claude-sonnet-4-5").sampling is True
        assert claude_traits("claude-sonnet-4-5").adaptive_thinking is False
        assert claude_traits("claude-sonnet-4-6").adaptive_thinking is True
        assert claude_traits("claude-sonnet-4-6").xhigh_effort is False
        assert claude_traits("claude-opus-4-7").sampling is False
        assert claude_traits("claude-opus-4-7").xhigh_effort is True


class TestOpenAiTemperatureWithoutReasoning:
    def test_a_model_that_can_stop_reasoning_keeps_temperature(self) -> None:
        register_model("gpt-9", {"provider": "openai", "supports_none_reasoning_effort": True})
        assert keeps_temperature_without_reasoning("gpt-9") is True

    def test_a_model_that_always_reasons_does_not(self) -> None:
        register_model("gpt-9", {"provider": "openai", "supports_none_reasoning_effort": False})
        assert keeps_temperature_without_reasoning("gpt-9") is False

    def test_an_unlisted_model_does_not(self) -> None:
        assert keeps_temperature_without_reasoning("gpt-99-unlisted") is False

    def test_the_bundled_snapshot_separates_gpt_5_from_gpt_5_1(self) -> None:
        assert keeps_temperature_without_reasoning("gpt-5") is False
        assert keeps_temperature_without_reasoning("gpt-5.1") is True


class TestGeminiGeneration:
    @pytest.mark.parametrize(
        ("model", "from_3"),
        [
            ("gemini-1.5-pro", False),
            ("gemini-2.0-flash", False),
            ("gemini-2.5-pro", False),
            ("gemini-3-pro-preview", True),
            ("gemini-3.1-pro-preview", True),
            ("gemini-3.8-flash", True),
            ("gemini-4-argon", True),
            ("gemini-10-pro", True),
            ("gemini-flash-latest", False),
            ("gemini-exp-1206", False),
            ("gpt-4o", False),
        ],
    )
    def test_the_generation_number_decides_not_a_gemini_3_prefix(self, model: str, from_3: bool) -> None:
        assert gemini_from_3(model) is from_3

    @pytest.mark.parametrize(
        ("model", "by_level"),
        [
            ("gemini-2.5-flash", False),
            ("gemini-3-pro-preview", True),
            ("gemini-4-argon", True),
            ("gemini-flash-latest", True),
            ("gemini-pro-latest", True),
            ("models/gemini-flash-lite-latest", True),
            ("gemini-exp-1206", False),
        ],
    )
    def test_later_generations_and_the_latest_aliases_think_by_level(self, model: str, by_level: bool) -> None:
        assert gemini_thinks_by_level(model) is by_level

    @pytest.mark.parametrize(
        ("model", "effort", "level"),
        [
            ("gemini-3-flash-preview", "minimal", "minimal"),
            ("gemini-3-flash-preview", "low", "low"),
            ("gemini-3.5-flash", "medium", "medium"),
            ("gemini-3-pro-preview", "minimal", "low"),
            ("gemini-3-pro-preview", "medium", "high"),
            ("gemini-3.1-pro-preview", "medium", "medium"),
            ("gemini-3.9-pro", "medium", "medium"),
            ("gemini-4-argon", "medium", "medium"),
            ("gemini-flash-latest", "medium", "medium"),
            ("gemini-pro-latest", "medium", "high"),
            ("gemini-3-pro-preview", "high", "high"),
            ("gemini-3-flash-preview", "xhigh", "high"),
        ],
    )
    def test_effort_maps_to_the_level_the_model_has(self, model: str, effort: str, level: str) -> None:
        assert gemini_thinking_level(model, effort) == level
