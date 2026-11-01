"""Model catalog: lookup rules, runtime registrations, cache-aware pricing and the bundled snapshot."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.catalog import (
    cost_per_token,
    known_models,
    model_info,
    register_model,
    store,
    supports_web_search,
)


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registrations a test makes never outlive it."""
    monkeypatch.setattr(store, "_REGISTERED", {})


class TestLookup:
    def test_an_exact_key_wins(self) -> None:
        register_model("vendor-a/model-x", {"provider": "vendor-a", "max_input_tokens": 1})
        register_model("model-x", {"provider": "vendor-b", "max_input_tokens": 2})
        assert (model_info("vendor-a/model-x") or {})["max_input_tokens"] == 1
        assert (model_info("model-x") or {})["max_input_tokens"] == 2

    def test_a_qualified_id_finds_the_providers_own_qualified_entry(self) -> None:
        register_model("vendor-a/model-q", {"provider": "vendor-a", "max_input_tokens": 10})
        assert (model_info("VENDOR-A/model-q") or {})["max_input_tokens"] == 10

    def test_a_qualified_id_finds_a_bare_entry_only_when_the_same_provider_owns_it(self) -> None:
        register_model("model-y", {"provider": "vendor-a", "max_input_tokens": 5})
        assert model_info("vendor-a/model-y") is not None
        assert model_info("vendor-b/model-y") is None

    def test_a_bare_id_without_a_hint_resolves_to_the_bare_entry(self) -> None:
        register_model("model-z", {"provider": "vendor-a"})
        assert model_info("model-z") is not None

    def test_a_provider_hint_finds_the_qualified_entry_of_a_bare_id(self) -> None:
        register_model("vendor-a/model-h", {"provider": "vendor-a", "max_input_tokens": 7})
        assert (model_info("model-h", "vendor-a") or {})["max_input_tokens"] == 7
        assert model_info("model-h", "vendor-b") is None

    def test_an_unknown_or_empty_id_has_no_entry(self) -> None:
        assert model_info("") is None
        assert model_info("no-such-model-anywhere") is None
        assert model_info("vendor-a/no-such-model-anywhere") is None


class TestRegistration:
    def test_a_registration_beats_the_snapshot_and_is_listed(self) -> None:
        register_model("gpt-4o", {"provider": "openai", "input_cost_per_token": 1.0})
        assert (model_info("gpt-4o") or {})["input_cost_per_token"] == 1.0
        assert known_models()["gpt-4o"]["input_cost_per_token"] == 1.0

    def test_the_stored_entry_is_a_copy(self) -> None:
        info: dict[str, object] = {"provider": "vendor-a", "max_tokens": 3}
        register_model("vendor-a/copy", info)
        info["max_tokens"] = 99
        assert (model_info("vendor-a/copy") or {})["max_tokens"] == 3


class TestSnapshot:
    def test_it_is_bundled_and_large(self) -> None:
        assert len(known_models()) > 1000

    @pytest.mark.parametrize("model", ["gpt-4o", "claude-sonnet-4-5", "deepseek-chat", "gemini-2.5-pro"])
    def test_flagship_models_carry_prices_and_a_window(self, model: str) -> None:
        info = model_info(model)
        assert info is not None
        assert isinstance(info["input_cost_per_token"], float) and info["input_cost_per_token"] > 0
        assert isinstance(info["output_cost_per_token"], float) and info["output_cost_per_token"] > 0
        assert isinstance(info["max_input_tokens"], int) and info["max_input_tokens"] > 0

    def test_every_entry_names_its_owning_provider_under_the_key_the_lookup_reads(self) -> None:
        assert all(isinstance(e.get("provider"), str) for e in known_models().values())
        assert all("litellm_provider" not in e for e in known_models().values())

    def test_native_search_flag_is_read_as_a_strict_boolean(self) -> None:
        assert supports_web_search("gpt-4o-search-preview")
        assert not supports_web_search("gpt-4o")
        assert not supports_web_search("no-such-model-anywhere")


class TestCost:
    @staticmethod
    def _register(**rates: object) -> None:
        register_model("vendor-a/priced", {"provider": "vendor-a", **rates})

    def test_plain_input_and_output(self) -> None:
        self._register(input_cost_per_token=2e-6, output_cost_per_token=6e-6)
        assert cost_per_token("vendor-a/priced", 1000, 500) == pytest.approx((2e-3, 3e-3))

    def test_cache_reads_and_writes_are_billed_at_their_own_rates(self) -> None:
        self._register(
            input_cost_per_token=2e-6,
            output_cost_per_token=6e-6,
            cache_read_input_token_cost=5e-7,
            cache_creation_input_token_cost=2.5e-6,
        )
        prompt, completion = cost_per_token(
            "vendor-a/priced", 1000, 0, cache_read_tokens=600, cache_write_tokens=100
        ) or (0, 0)
        # 300 fresh @ 2/M + 600 read @ 0.5/M + 100 written @ 2.5/M
        assert prompt == pytest.approx(300 * 2e-6 + 600 * 5e-7 + 100 * 2.5e-6)
        assert completion == 0

    def test_an_unlisted_cache_price_is_billed_at_the_input_rate_not_for_free(self) -> None:
        self._register(input_cost_per_token=2e-6, output_cost_per_token=6e-6)
        prompt, _ = cost_per_token("vendor-a/priced", 1000, 0, cache_read_tokens=1000) or (0, 0)
        assert prompt == pytest.approx(1000 * 2e-6)

    def test_cached_counts_are_clamped_to_the_prompt(self) -> None:
        self._register(input_cost_per_token=1e-6, output_cost_per_token=1e-6, cache_read_input_token_cost=1e-7)
        prompt, _ = cost_per_token("vendor-a/priced", 100, 0, cache_read_tokens=500, cache_write_tokens=500) or (0, 0)
        assert prompt == pytest.approx(100 * 1e-7)

    def test_a_long_prompt_switches_every_rate_to_the_higher_tier(self) -> None:
        self._register(
            input_cost_per_token=1e-6,
            output_cost_per_token=2e-6,
            input_cost_per_token_above_200k_tokens=2e-6,
            output_cost_per_token_above_200k_tokens=4e-6,
        )
        assert cost_per_token("vendor-a/priced", 200_000, 10) == pytest.approx((0.2, 20e-6))
        assert cost_per_token("vendor-a/priced", 200_001, 10) == pytest.approx((200_001 * 2e-6, 40e-6))

    def test_an_unpriced_or_partially_priced_model_has_no_cost(self) -> None:
        self._register(input_cost_per_token=1e-6)
        assert cost_per_token("vendor-a/priced", 10, 10) is None
        assert cost_per_token("no-such-model-anywhere", 10, 10) is None

    def test_negative_counts_never_produce_negative_cost(self) -> None:
        self._register(input_cost_per_token=1e-6, output_cost_per_token=1e-6)
        prompt, completion = cost_per_token("vendor-a/priced", -5, -5) or (1, 1)
        assert prompt == 0 and completion == 0
