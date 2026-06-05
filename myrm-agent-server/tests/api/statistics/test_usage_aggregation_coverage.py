from app.api.statistics.usage_aggregation import DayAccumulator, TierAccumulator


def test_day_accumulator_cache_break():
    acc = DayAccumulator()
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "cached_tokens": 80, "total_tokens": 150}
    extra_data = {
        "costUsd": 0.02,
        "tokenEconomics": {"total_cache_savings_usd": 0.005},
        "cacheBreak": {"raw_reasons": ["ttl_expiry", "system_prompt_changed", "ttl_expiry"]},
    }

    acc.add(usage, extra_data)

    assert acc.input_tokens == 100
    assert acc.output_tokens == 50
    assert acc.cached_tokens == 80
    assert acc.total_tokens == 150
    assert acc.cost_usd == 0.02
    assert acc.cache_savings_usd == 0.005
    assert acc.cache_break_counts == {"ttl_expiry": 2, "system_prompt_changed": 1}

    data = acc.to_dict()
    assert data["cacheBreakCounts"] == {"ttl_expiry": 2, "system_prompt_changed": 1}
    assert data["cacheSavingsUsd"] == 0.005


def test_tier_accumulator():
    acc = TierAccumulator()
    usage = {"total_tokens": 100}
    extra_data = {"costUsd": 0.01}
    acc.add(usage, extra_data)
    assert acc.calls == 1
    assert acc.total_tokens == 100
    assert acc.cost_usd == 0.01
    assert acc.to_dict() == {"calls": 1, "totalTokens": 100, "costUsd": 0.01}
