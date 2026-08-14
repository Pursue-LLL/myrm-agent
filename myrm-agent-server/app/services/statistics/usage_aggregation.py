"""Usage aggregation pure logic shared by statistics API and chat usage sync.

[INPUT]
- app.services.chat.chat_message (POS: chat 消息写入时的 tokenEconomics 快照)
- assistant message extra_data snapshots (POS: 会话级用量原始数据)

[OUTPUT]
- app.api.statistics.usage_aggregation (POS: API 层 re-export 薄壳)
- aggregate_chat_usage_rows: Chat.total_* O(1) 用量缓存重建
- aggregate_usage: 会话级统计聚合（路由/模型/隐私/cache 维度）

[POS]
Business-layer usage aggregation. 纯聚合逻辑必须位于 services 层，
API 层仅做装配与暴露；服务层不得反向 import app.api。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from math import ceil
from typing import cast


def normalize_usage_rows(
    rows: Sequence[object],
) -> list[tuple[dict[str, object] | None, datetime | None]]:
    """Coerce SQLAlchemy Row / tuple results into aggregate_usage inputs."""
    normalized: list[tuple[dict[str, object] | None, datetime | None]] = []
    for row in rows:
        cells: tuple[object, ...] = tuple(cast(Sequence[object], row))
        if not cells:
            continue
        raw_extra = cells[0]
        raw_dt = cells[1] if len(cells) > 1 else None
        extra_dict = raw_extra if isinstance(raw_extra, dict) else None
        dt_val = raw_dt if isinstance(raw_dt, datetime) else None
        normalized.append((extra_dict, dt_val))
    return normalized


def extract_usage(extra_data: dict[str, object] | None) -> dict[str, object] | None:
    """Extract the usage dict from message extra_data."""
    if not extra_data or not isinstance(extra_data, dict):
        return None
    usage = extra_data.get("usage")
    return usage if isinstance(usage, dict) else None


class DayAccumulator:
    """Lightweight accumulator for usage stats."""

    __slots__ = (
        "calls",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "citation_tokens",
        "total_tokens",
        "cost_usd",
        "cache_savings_usd",
        "cache_break_counts",
    )

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.reasoning_tokens = 0
        self.citation_tokens = 0
        self.total_tokens = 0
        self.cost_usd = 0.0
        self.cache_savings_usd = 0.0
        self.cache_break_counts: dict[str, int] = {}

    def add(self, usage: dict[str, object], extra_data: dict[str, object] | None) -> None:
        self.calls += 1
        self.input_tokens += to_int(usage.get("prompt_tokens"))
        self.output_tokens += to_int(usage.get("completion_tokens"))
        self.cached_tokens += to_int(usage.get("cached_tokens"))
        self.reasoning_tokens += to_int(usage.get("reasoning_tokens"))
        self.citation_tokens += to_int(usage.get("citation_tokens"))
        self.total_tokens += to_int(usage.get("total_tokens"))
        if extra_data:
            cost_raw = extra_data.get("costUsd")
            if isinstance(cost_raw, (int, float)):
                self.cost_usd += float(cost_raw)
            token_economics = extra_data.get("tokenEconomics")
            if isinstance(token_economics, dict):
                cache_savings = token_economics.get("total_cache_savings_usd")
                if isinstance(cache_savings, (int, float)):
                    self.cache_savings_usd += float(cache_savings)
            cache_break = extra_data.get("cacheBreak")
            if isinstance(cache_break, dict):
                raw_reasons = cache_break.get("raw_reasons")
                if isinstance(raw_reasons, list):
                    for reason_key in raw_reasons:
                        if isinstance(reason_key, str) and reason_key:
                            self.cache_break_counts[reason_key] = self.cache_break_counts.get(reason_key, 0) + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "cachedTokens": self.cached_tokens,
            "reasoningTokens": self.reasoning_tokens,
            "citationTokens": self.citation_tokens,
            "totalTokens": self.total_tokens,
            "costUsd": round(self.cost_usd, 6),
            "cacheSavingsUsd": round(self.cache_savings_usd, 6),
            "cacheBreakCounts": self.cache_break_counts,
        }


def to_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def to_float(value: object) -> float:
    """Coerce a numeric value to float, returning 0.0 for invalid/None input.

    Accepts int/float and numeric strings (some model metadata reports costs
    as strings); bool and non-numeric values are treated as 0.0.
    """
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def extract_stream_ttft_ms(extra_data: dict[str, object] | None) -> int | None:
    if not extra_data or not isinstance(extra_data, dict):
        return None
    raw = extra_data.get("streamTtftMs")
    if isinstance(raw, (int, float)) and raw >= 0:
        return int(raw)
    return None


def build_stream_ttft_summary(samples: list[int]) -> dict[str, object] | None:
    if not samples:
        return None
    ordered = sorted(samples)
    sample_count = len(ordered)
    average_ms = round(sum(ordered) / sample_count, 2)
    p95_index = max(0, min(sample_count - 1, ceil(sample_count * 0.95) - 1))
    p95_ms = ordered[p95_index]
    return {
        "sampleCount": sample_count,
        "avgMs": average_ms,
        "p95Ms": p95_ms,
    }


_VALID_ROUTING_TIERS = frozenset({"simple", "standard", "reasoning"})
_TIER_NORMALIZE: dict[str, str] = {"complex": "standard"}
_MIN_STANDARD_CALLS_FOR_SAVINGS = 5


def normalize_tier(raw: object) -> str | None:
    """Normalize routing tier value, mapping legacy 'complex' to 'standard'."""
    if not isinstance(raw, str):
        return None
    tier = _TIER_NORMALIZE.get(raw, raw)
    return tier if tier in _VALID_ROUTING_TIERS else None


class TierAccumulator:
    """Per-tier statistics accumulator."""

    __slots__ = ("calls", "total_tokens", "cost_usd")

    def __init__(self) -> None:
        self.calls = 0
        self.total_tokens = 0
        self.cost_usd = 0.0

    def add(self, usage: dict[str, object], extra_data: dict[str, object] | None) -> None:
        self.calls += 1
        self.total_tokens += to_int(usage.get("total_tokens"))
        if extra_data:
            cost_raw = extra_data.get("costUsd")
            if isinstance(cost_raw, (int, float)):
                self.cost_usd += float(cost_raw)

    def to_dict(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "totalTokens": self.total_tokens,
            "costUsd": round(self.cost_usd, 6),
        }


def compute_estimated_savings(
    tier_accs: dict[str, TierAccumulator],
) -> dict[str, object] | None:
    """Estimate cost savings from routing vs. using the standard model for all queries."""
    standard = tier_accs.get("standard")
    if not standard or standard.calls < _MIN_STANDARD_CALLS_FOR_SAVINGS:
        return None

    avg_cost_per_call = standard.cost_usd / standard.calls
    total_routed_calls = sum(acc.calls for acc in tier_accs.values())
    actual_total_cost = sum(acc.cost_usd for acc in tier_accs.values())
    hypothetical_cost = total_routed_calls * avg_cost_per_call
    savings = hypothetical_cost - actual_total_cost
    if savings <= 0:
        return None

    return {
        "actualCost": round(actual_total_cost, 6),
        "hypotheticalCost": round(hypothetical_cost, 6),
        "savings": round(savings, 6),
        "savingsPercent": round(savings / hypothetical_cost * 100, 1) if hypothetical_cost > 0 else 0.0,
    }


def aggregate_usage(
    rows: Sequence[tuple[dict[str, object] | None, datetime | None]],
) -> dict[str, object]:
    """Aggregate usage data from message extra_data rows."""
    acc = DayAccumulator()
    model_breakdown: dict[str, dict[str, int | float]] = {}
    tier_accs: dict[str, TierAccumulator] = {}
    privacy_route_counts: dict[str, int] = {}
    stream_ttft_samples: list[int] = []

    for extra_data, _ in rows:
        extra = extra_data if isinstance(extra_data, dict) else None
        stream_ttft = extract_stream_ttft_ms(extra)
        if stream_ttft is not None:
            stream_ttft_samples.append(stream_ttft)

        usage = extract_usage(extra_data)
        if not usage:
            continue

        acc.add(usage, extra)

        tier = normalize_tier(extra.get("routingTier")) if extra else None
        if tier:
            if tier not in tier_accs:
                tier_accs[tier] = TierAccumulator()
            tier_accs[tier].add(usage, extra)

        privacy_route = extra.get("privacyRoute") if extra else None
        if isinstance(privacy_route, str) and privacy_route:
            route_bucket = "local" if "local" in privacy_route else "cloud"
            privacy_route_counts[route_bucket] = privacy_route_counts.get(route_bucket, 0) + 1

        model_usage = usage.get("model_usage")
        if not isinstance(model_usage, dict):
            continue

        for model, model_data in model_usage.items():
            if not isinstance(model_data, dict):
                continue
            if model not in model_breakdown:
                model_breakdown[model] = {
                    "calls": 0,
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cachedTokens": 0,
                    "totalTokens": 0,
                    "costUsd": 0.0,
                }
            bucket = model_breakdown[model]
            bucket["calls"] = int(bucket["calls"]) + 1
            bucket["inputTokens"] = int(bucket["inputTokens"]) + to_int(model_data.get("prompt_tokens"))
            bucket["outputTokens"] = int(bucket["outputTokens"]) + to_int(model_data.get("completion_tokens"))
            bucket["cachedTokens"] = int(bucket["cachedTokens"]) + to_int(model_data.get("cached_tokens"))
            bucket["totalTokens"] = int(bucket["totalTokens"]) + to_int(model_data.get("total_tokens"))
            bucket["costUsd"] = round(
                float(bucket["costUsd"])
                + (float(model_data["cost_usd"]) if isinstance(model_data.get("cost_usd"), (int, float)) else 0.0),
                6,
            )

    cache_hit_rate = acc.cached_tokens / acc.input_tokens if acc.input_tokens > 0 else 0.0
    result: dict[str, object] = {
        **acc.to_dict(),
        "cacheHitRate": round(cache_hit_rate, 4),
        "modelBreakdown": model_breakdown,
    }
    if tier_accs:
        result["routingBreakdown"] = {tier: acc.to_dict() for tier, acc in tier_accs.items()}
        savings = compute_estimated_savings(tier_accs)
        if savings:
            result["estimatedSavings"] = savings
    if privacy_route_counts:
        result["privacyRouteBreakdown"] = privacy_route_counts
    stream_ttft_summary = build_stream_ttft_summary(stream_ttft_samples)
    if stream_ttft_summary is not None:
        result["streamTtft"] = stream_ttft_summary
    return result


def aggregate_chat_usage_rows(
    extras: Sequence[dict[str, object] | None],
) -> dict[str, int | float]:
    """Aggregate per-session usage from assistant message extra_data.

    Each assistant message persists the turn-level ``tokenEconomics`` snapshot
    (harness ``tracker.to_dict()`` with exact call_count / total_cost_usd /
    usage.total_tokens) at write time. Summing snapshots yields the session
    cumulative usage that Chat.total_* caches. Legacy messages without the
    snapshot fall back to ``usage`` / ``costUsd``.

    Returns:
        {"total_calls": int, "total_tokens": int, "total_usd": float}
    """
    total_calls = 0
    total_tokens = 0
    total_usd = 0.0
    for extra in extras:
        if not isinstance(extra, dict):
            continue
        token_economics = extra.get("tokenEconomics")
        if isinstance(token_economics, dict):
            total_calls += to_int(token_economics.get("call_count"))
            usage = token_economics.get("usage")
            if isinstance(usage, dict):
                total_tokens += to_int(usage.get("total_tokens"))
            total_usd += to_float(token_economics.get("total_cost_usd"))
            continue
        usage = extract_usage(extra)
        if isinstance(usage, dict):
            total_calls += 1
            total_tokens += to_int(usage.get("total_tokens"))
        total_usd += to_float(extra.get("costUsd"))
    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_usd": round(total_usd, 6),
    }


__all__ = [
    "DayAccumulator",
    "TierAccumulator",
    "aggregate_chat_usage_rows",
    "aggregate_usage",
    "compute_estimated_savings",
    "build_stream_ttft_summary",
    "extract_stream_ttft_ms",
    "extract_usage",
    "normalize_tier",
    "normalize_usage_rows",
    "to_float",
    "to_int",
]
