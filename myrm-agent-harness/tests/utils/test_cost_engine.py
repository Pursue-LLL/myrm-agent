"""Tests for myrm_agent_harness.utils.token_economics.cost_engine (catalog-priced)."""

from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.llms.catalog import register_model, store
from myrm_agent_harness.utils.token_economics.cost_engine import (
    CostResult,
    CostStatus,
    compute_cost_by_tokens,
)


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(store, "_REGISTERED", {})
    yield


class TestCostResult:
    def test_defaults(self) -> None:
        r = CostResult()
        assert r.usd == 0.0
        assert r.status == CostStatus.UNKNOWN

    @pytest.mark.parametrize("status", [CostStatus.ACTUAL, CostStatus.ESTIMATED])
    def test_priced_status_is_known(self, status: CostStatus) -> None:
        assert CostResult(usd=0.01, status=status).is_known is True

    def test_unknown_is_not_known(self) -> None:
        assert CostResult().is_known is False


class TestUnpriced:
    def test_no_model(self) -> None:
        assert compute_cost_by_tokens(None, 100, 50) == CostResult()
        assert compute_cost_by_tokens("", 100, 50) == CostResult()

    def test_no_tokens(self) -> None:
        assert compute_cost_by_tokens("gpt-4o", 0, 0) == CostResult()
        assert compute_cost_by_tokens("gpt-4o", -1, -1) == CostResult()

    def test_model_missing_from_catalog_is_unknown_not_free(self) -> None:
        assert compute_cost_by_tokens("no-such-model-xyz", 100, 50) == CostResult()

    def test_zero_priced_entry_is_unknown(self) -> None:
        register_model("free-model", {"input_cost_per_token": 0.0, "output_cost_per_token": 0.0})
        assert compute_cost_by_tokens("free-model", 100, 50) == CostResult()


class TestPriced:
    def test_mainstream_model_bills_actual(self) -> None:
        # gpt-4o: 1k prompt @ 2.50/M + 200 completion @ 10.00/M
        result = compute_cost_by_tokens("gpt-4o", 1000, 200)
        assert result.status == CostStatus.ACTUAL
        assert result.usd == pytest.approx(0.0045, abs=1e-6)

    def test_cache_read_is_discounted(self) -> None:
        uncached = compute_cost_by_tokens("gpt-4o", 1000, 200)
        cached = compute_cost_by_tokens("gpt-4o", 1000, 200, cache_read_tokens=800)
        assert cached.usd < uncached.usd
        assert cached.usd == pytest.approx(0.0035, abs=1e-6)

    def test_only_prompt_tokens(self) -> None:
        result = compute_cost_by_tokens("gpt-4o", 100, 0)
        assert result.status == CostStatus.ACTUAL
        assert result.usd == pytest.approx(0.00025, abs=1e-8)

    def test_only_completion_tokens(self) -> None:
        result = compute_cost_by_tokens("gpt-4o", 0, 100)
        assert result.status == CostStatus.ACTUAL
        assert result.usd == pytest.approx(0.001, abs=1e-8)

    def test_provider_qualified_name(self) -> None:
        result = compute_cost_by_tokens("deepseek/deepseek-chat", 5000, 1000)
        assert result.status == CostStatus.ACTUAL
        assert result.usd > 0.0

    def test_request_model_wins_over_response_model(self) -> None:
        by_request = compute_cost_by_tokens("unknown-alias", 1000, 200, request_model="gpt-4o")
        assert by_request.usd == pytest.approx(0.0045, abs=1e-6)

    def test_registered_price_beats_snapshot_and_bills_cache(self) -> None:
        register_model(
            "custom_openai/mimo-test",
            {
                "input_cost_per_token": 0.000002,
                "output_cost_per_token": 0.000006,
                "cache_read_input_token_cost": 0.0000005,
            },
        )
        result = compute_cost_by_tokens("custom_openai/mimo-test", 1000, 500, cache_read_tokens=800)
        # 800 cached @ 0.5/M + 200 fresh @ 2/M + 500 completion @ 6/M
        assert result.usd == pytest.approx(0.0038, abs=1e-8)
        assert result.status == CostStatus.ACTUAL


class TestGatewayFallback:
    def test_gateway_prefix_is_estimated_from_the_stripped_name(self) -> None:
        result = compute_cost_by_tokens("my-gateway/gpt-4o", 1000, 200)
        assert result.status == CostStatus.ESTIMATED
        assert result.usd == pytest.approx(0.0045, abs=1e-6)

    def test_unknown_after_stripping_stays_unknown(self) -> None:
        assert compute_cost_by_tokens("my-gateway/no-such-model-xyz", 1000, 200) == CostResult()

    def test_other_providers_price_is_never_used_as_actual(self) -> None:
        # "deepseek/gpt-4o" must not bill gpt-4o's OpenAI price as the vendor's own price.
        result = compute_cost_by_tokens("deepseek/gpt-4o", 1000, 200)
        assert result.status != CostStatus.ACTUAL
