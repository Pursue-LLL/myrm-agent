"""Tests for token_economics.cache_savings (catalog-priced)."""

from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.llms.catalog import register_model, store
from myrm_agent_harness.utils.token_economics.cache_savings import calculate_cache_savings_usd

_CACHING = "caching-model"
_NO_CACHE_PRICE = "model-no-cache-cost"


@pytest.fixture(autouse=True)
def _catalog(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(store, "_REGISTERED", {})
    register_model(
        _CACHING,
        {
            "input_cost_per_token": 0.000003,
            "output_cost_per_token": 0.000015,
            "cache_read_input_token_cost": 0.0000003,
            "cache_creation_input_token_cost": 0.00000375,
        },
    )
    register_model(_NO_CACHE_PRICE, {"input_cost_per_token": 0.000003, "output_cost_per_token": 0.000015})
    yield


def _details(cached: int = 0, created: int = 0) -> dict[str, object]:
    return {"prompt_tokens_details": {"cached_tokens": cached, "cache_creation_input_tokens": created}}


def test_empty_model_returns_zero() -> None:
    assert calculate_cache_savings_usd({"cached_tokens": 100}, None) == 0.0
    assert calculate_cache_savings_usd({"cached_tokens": 100}, "") == 0.0


def test_empty_usage_returns_zero() -> None:
    assert calculate_cache_savings_usd({}, _CACHING) == 0.0


def test_no_cached_tokens_returns_zero() -> None:
    assert calculate_cache_savings_usd(_details(0, 0), _CACHING) == 0.0


def test_read_discount_minus_write_premium() -> None:
    # gross 1000 * (3e-6 - 3e-7) = 0.0027; premium 500 * (3.75e-6 - 3e-6) = 0.000375
    assert calculate_cache_savings_usd(_details(1000, 500), _CACHING) == pytest.approx(0.002325, abs=1e-9)


def test_negative_roi_when_only_writing() -> None:
    savings = calculate_cache_savings_usd(_details(0, 1000), _CACHING)
    assert savings == pytest.approx(-0.00075, abs=1e-9)


def test_flat_cached_tokens_field_is_the_fallback() -> None:
    savings = calculate_cache_savings_usd({"cached_tokens": 1000}, _CACHING)
    assert savings == pytest.approx(0.0027, abs=1e-9)


def test_model_without_cache_read_price_returns_zero() -> None:
    assert calculate_cache_savings_usd(_details(1000), _NO_CACHE_PRICE) == 0.0


def test_unknown_model_returns_zero() -> None:
    assert calculate_cache_savings_usd(_details(500), "totally-unknown") == 0.0
