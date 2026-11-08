"""Prices by prompt size: ``tiered_pricing`` bills the whole request at the tier its prompt falls in."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.catalog import cost_per_token, known_models, model_info, register_model

# Qwen3-Max as the vendor publishes it, USD per token: the tier follows the request's total input tokens.
_QWEN3_MAX = [
    {"range": [0, 32000], "input_cost_per_token": 1.2e-6, "output_cost_per_token": 6e-6},
    {"range": [32000, 128000], "input_cost_per_token": 2.4e-6, "output_cost_per_token": 1.2e-5},
    {"range": [128000, 252000], "input_cost_per_token": 3e-6, "output_cost_per_token": 1.5e-5},
]
_MODEL = "vendor-a/tiered"
_COUNT_FIELDS = ("max_tokens", "max_input_tokens", "max_output_tokens", "output_vector_size")


def _register(tiers: object, **flat: object) -> None:
    register_model(_MODEL, {"provider": "vendor-a", "tiered_pricing": tiers, **flat})


def _priced(
    prompt: int, completion: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0
) -> tuple[float, float]:
    cost = cost_per_token(
        _MODEL, prompt, completion, cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens
    )
    assert cost is not None, "the model is unpriced"
    return cost


class TestTierSelection:
    @pytest.mark.parametrize(
        ("prompt", "completion", "bill"),
        [(20_000, 800, 0.0288), (50_000, 1_000, 0.132), (130_000, 1_000, 0.405), (250_000, 1_000, 0.765)],
    )
    def test_the_whole_request_is_billed_at_the_tier_its_prompt_falls_in(
        self, prompt: int, completion: int, bill: float
    ) -> None:
        _register(_QWEN3_MAX)
        assert sum(_priced(prompt, completion)) == pytest.approx(bill)

    @pytest.mark.parametrize(
        ("prompt", "input_rate"),
        [(1, 1.2e-6), (32_000, 1.2e-6), (32_001, 2.4e-6), (128_000, 2.4e-6), (128_001, 3e-6)],
    )
    def test_a_prompt_on_the_upper_edge_of_a_tier_belongs_to_that_tier(self, prompt: int, input_rate: float) -> None:
        _register(_QWEN3_MAX)
        assert _priced(prompt, 0)[0] == pytest.approx(prompt * input_rate)

    def test_a_prompt_beyond_the_last_tier_is_billed_at_the_last_one(self) -> None:
        _register(_QWEN3_MAX)
        assert _priced(5_000_000, 10) == pytest.approx((5_000_000 * 3e-6, 10 * 1.5e-5))

    @pytest.mark.parametrize("prompt", [0, -5])
    def test_an_empty_prompt_is_billed_at_the_first_tier(self, prompt: int) -> None:
        _register(_QWEN3_MAX)
        assert _priced(prompt, 10) == pytest.approx((0, 10 * 6e-6))

    def test_tiers_listed_in_any_order_apply_by_their_range(self) -> None:
        _register(list(reversed(_QWEN3_MAX)))
        assert sum(_priced(50_000, 1_000)) == pytest.approx(0.132)

    def test_the_cache_rate_of_the_tier_applies_and_an_unlisted_one_is_the_tier_input_rate_not_free(self) -> None:
        _register(
            [
                {"range": [0, 100], "input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6},
                {
                    "range": [100, 200],
                    "input_cost_per_token": 2e-6,
                    "output_cost_per_token": 4e-6,
                    "cache_read_input_token_cost": 5e-7,
                    "cache_creation_input_token_cost": 2.5e-6,
                },
            ]
        )
        assert _priced(50, 0, cache_read_tokens=50)[0] == pytest.approx(50 * 1e-6)
        assert _priced(150, 0, cache_read_tokens=100, cache_write_tokens=20)[0] == pytest.approx(
            30 * 2e-6 + 100 * 5e-7 + 20 * 2.5e-6
        )

    def test_the_rates_of_a_tier_are_never_mixed_with_flat_ones_the_entry_also_states(self) -> None:
        _register(
            _QWEN3_MAX,
            input_cost_per_token=9.0,
            output_cost_per_token=9.0,
            cache_read_input_token_cost=1e-9,
            input_cost_per_token_above_200k_tokens=9.0,
        )
        assert sum(_priced(20_000, 800)) == pytest.approx(0.0288)
        assert _priced(220_000, 0, cache_read_tokens=1000)[0] == pytest.approx(220_000 * 3e-6)

    @pytest.mark.parametrize(
        "tiers",
        [
            [],
            "dear",
            [3],
            [{"range": [0, 10]}],
            [{"range": [0, 10], "input_cost_per_token": 1e-6}],
            [{"range": [0, 10], "output_cost_per_token": 1e-6}],
            [{"input_cost_per_token": 1e-6, "output_cost_per_token": 1e-6}],
            [{"range": ["a", "b"], "input_cost_per_token": 1e-6, "output_cost_per_token": 1e-6}],
            [{"range": [5], "input_cost_per_token": 1e-6, "output_cost_per_token": 1e-6}],
            7,
        ],
        ids=[
            "empty",
            "not a list",
            "not a row",
            "no rates",
            "no output rate",
            "no input rate",
            "no range",
            "no bounds",
            "one bound",
            "a number",
        ],
    )
    def test_tiers_that_cannot_be_used_leave_the_flat_price_or_no_price(self, tiers: object) -> None:
        _register(tiers)
        assert cost_per_token(_MODEL, 10, 10) is None
        _register(tiers, input_cost_per_token=1e-6, output_cost_per_token=2e-6)
        assert _priced(10, 10) == pytest.approx((1e-5, 2e-5))

    def test_one_unusable_row_does_not_hide_the_usable_ones(self) -> None:
        _register([{"range": [0, 10]}, *_QWEN3_MAX])
        assert sum(_priced(20_000, 800)) == pytest.approx(0.0288)


class TestRegistration:
    def test_stated_tiers_replace_the_flat_prices_of_the_entry_they_overlay(self) -> None:
        assert "input_cost_per_token" in (model_info("gpt-4o") or {})
        register_model("gpt-4o", {"provider": "openai", "tiered_pricing": _QWEN3_MAX})
        info = model_info("gpt-4o") or {}
        assert not {field for field in info if "_cost" in field}
        assert cost_per_token("gpt-4o", 20_000, 800) == pytest.approx((20_000 * 1.2e-6, 800 * 6e-6))

    def test_stated_flat_prices_replace_the_tiers_of_the_entry_they_overlay(self) -> None:
        assert "tiered_pricing" in (model_info("dashscope/qwen3-max") or {})
        register_model(
            "dashscope/qwen3-max",
            {"provider": "dashscope", "input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6},
        )
        assert "tiered_pricing" not in (model_info("dashscope/qwen3-max") or {})
        assert cost_per_token("dashscope/qwen3-max", 200_000, 10) == pytest.approx((0.2, 2e-5))

    def test_a_registration_that_states_no_price_keeps_the_tiers(self) -> None:
        register_model("dashscope/qwen3-max", {"provider": "dashscope", "max_input_tokens": 1000})
        assert cost_per_token("dashscope/qwen3-max", 20_000, 800) == pytest.approx((0.024, 0.0048))


def _tiered_models() -> dict[str, dict[str, object]]:
    return {key: dict(entry) for key, entry in known_models().items() if "tiered_pricing" in entry}


class TestShippedSnapshot:
    def test_it_carries_the_tiers_of_the_models_that_state_their_prices_that_way(self) -> None:
        tiered = _tiered_models()
        assert len(tiered) >= 54
        assert {
            "dashscope/qwen3-max",
            "dashscope/qwen3-coder-plus",
            "volcengine/doubao-seed-2-0-pro-260215",
        } <= tiered.keys()

    def test_every_tier_table_is_whole_ascending_and_contiguous_from_zero(self) -> None:
        for key, entry in _tiered_models().items():
            rows = entry["tiered_pricing"]
            assert isinstance(rows, list) and rows, key
            previous_top = 0
            for row in rows:
                assert isinstance(row, dict), key
                low, high = row["range"]
                assert low == previous_top and high > low, f"{key}: {row['range']}"
                previous_top = high
                assert row["input_cost_per_token"] > 0 and row["output_cost_per_token"] > 0, key

    def test_every_tiered_model_is_priced_at_every_prompt_size(self) -> None:
        for key in _tiered_models():
            for prompt in (1, 20_000, 200_000, 20_000_000):
                assert cost_per_token(key, prompt, 1) is not None, f"{key} at {prompt} tokens"

    def test_a_model_priced_only_by_tiers_is_billed_as_the_vendor_publishes_it(self) -> None:
        # dashscope/qwen3-max: input 1.2 / 2.4 / 3.0 and output 6 / 12 / 15 USD per million tokens by prompt size.
        assert sum(cost_per_token("dashscope/qwen3-max", 20_000, 800) or ()) == pytest.approx(0.0288)
        assert sum(cost_per_token("dashscope/qwen3-max", 50_000, 1_000) or ()) == pytest.approx(0.132)
        assert sum(cost_per_token("dashscope/qwen3-max", 130_000, 1_000) or ()) == pytest.approx(0.405)

    def test_windows_and_vector_sizes_are_integers_every_reader_of_the_snapshot_accepts(self) -> None:
        for key, entry in known_models().items():
            for field in _COUNT_FIELDS:
                if field in entry:
                    assert isinstance(entry[field], int) and not isinstance(entry[field], bool), f"{key}.{field}"
