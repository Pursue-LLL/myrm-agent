from app.api.statistics.usage_aggregation import (
    DayAccumulator,
    TierAccumulator,
    aggregate_chat_usage_rows,
    aggregate_usage,
    to_float,
)


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


def test_aggregate_usage_includes_stream_ttft_summary():
    rows = [
        (
            {
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "streamTtftMs": 120,
            },
            None,
        ),
        (
            {
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
                "streamTtftMs": 80,
            },
            None,
        ),
        (
            {
                "usage": {"prompt_tokens": 6, "completion_tokens": 3, "total_tokens": 9},
                "streamTtftMs": 150,
            },
            None,
        ),
    ]
    result = aggregate_usage(rows)
    stream_ttft = result.get("streamTtft")
    assert isinstance(stream_ttft, dict)
    assert stream_ttft["sampleCount"] == 3
    assert stream_ttft["avgMs"] == 116.67
    assert stream_ttft["p95Ms"] == 150


def test_aggregate_usage_collects_stream_ttft_without_usage():
    rows = [
        (
            {
                "streamTtftMs": 40,
            },
            None,
        ),
        (
            {
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                "streamTtftMs": 80,
            },
            None,
        ),
    ]
    result = aggregate_usage(rows)
    stream_ttft = result.get("streamTtft")
    assert isinstance(stream_ttft, dict)
    assert stream_ttft["sampleCount"] == 2
    assert stream_ttft["avgMs"] == 60.0
    assert stream_ttft["p95Ms"] == 80
    assert result["calls"] == 1


def test_aggregate_chat_usage_rows_sums_token_economics_snapshots():
    extras = [
        {
            "tokenEconomics": {
                "call_count": 5,
                "total_cost_usd": 0.2,
                "usage": {"total_tokens": 6000},
            }
        },
        {
            "tokenEconomics": {
                "call_count": 3,
                "total_cost_usd": 0.15,
                "usage": {"total_tokens": 1200},
            }
        },
    ]
    result = aggregate_chat_usage_rows(extras)
    assert result == {"total_calls": 8, "total_tokens": 7200, "total_usd": 0.35}


def test_aggregate_chat_usage_rows_skips_missing_and_non_dict_entries():
    extras: list[dict[str, object] | None] = [
        None,
        "not-a-dict",
        42,
        {},
        {"tokenEconomics": {"call_count": 1, "usage": {"total_tokens": 10}, "total_cost_usd": 0.001}},
    ]
    result = aggregate_chat_usage_rows(extras)
    assert result == {"total_calls": 1, "total_tokens": 10, "total_usd": 0.001}


def test_aggregate_chat_usage_rows_empty_input_is_zero():
    assert aggregate_chat_usage_rows([]) == {
        "total_calls": 0,
        "total_tokens": 0,
        "total_usd": 0.0,
    }


def test_aggregate_chat_usage_rows_falls_back_to_legacy_usage():
    extras = [
        {"usage": {"total_tokens": 300}, "costUsd": 0.03},
        {"usage": {"total_tokens": 700}, "costUsd": 0.07},
    ]
    result = aggregate_chat_usage_rows(extras)
    assert result == {"total_calls": 2, "total_tokens": 1000, "total_usd": 0.1}


def test_aggregate_chat_usage_rows_handles_partial_snapshots():
    extras = [
        {"tokenEconomics": {"call_count": 2}},
        {"usage": {"total_tokens": 5}, "costUsd": 0.01},
    ]
    result = aggregate_chat_usage_rows(extras)
    assert result == {"total_calls": 3, "total_tokens": 5, "total_usd": 0.01}


def test_to_float_rejects_non_numeric_values():
    assert to_float(None) == 0.0
    assert to_float("1.5") == 0.0
    assert to_float(True) == 0.0
    assert to_float(False) == 0.0
    assert to_float(3) == 3.0
    assert to_float(2.5) == 2.5
