"""Cache health sampling and provider retention observation.

[INPUT]
- collections.abc::Mapping (POS: message usage metric payloads)
- myrm_agent_harness.agent.context_management.infra.cache_policy

[OUTPUT]
- CacheHealth: API DTO for cache-health status and observation sample.
- build_cache_health: Build cache status from aggregate and per-model usage metrics.

[POS]
Statistics API cache-health layer. Owns provider/model sample selection so the
context-health aggregate can stay focused on composition.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from myrm_agent_harness.agent.context_management.infra.cache_policy import resolve_cache_ttl_prune_policy

HealthStatus = Literal["inactive", "healthy", "warning", "critical"]
RetentionObservationState = Literal["observed", "estimated", "insufficient_data"]
RetentionObservationSampleSource = Literal["dominant_model", "session_aggregate"]

_CACHE_ACTIVE_MIN_CALLS = 2
_CACHE_ACTIVE_MIN_INPUT_TOKENS = 4_000
_CACHE_HEALTHY_HIT_RATE = 0.35
_CACHE_WARNING_HIT_RATE = 0.12
_MODEL_ROUTE_PREFIXES = frozenset(
    {
        "alibaba",
        "anthropic",
        "azure",
        "azure-openai",
        "bedrock",
        "dashscope",
        "deepseek",
        "gemini",
        "google",
        "google-gemini-cli",
        "nous",
        "openai",
        "opencode",
        "opencode-go",
        "openrouter",
        "qwen",
        "vertex",
    }
)


@dataclass(frozen=True, slots=True)
class CacheHealth:
    status: HealthStatus
    active: bool
    calls: int
    input_tokens: int
    cached_tokens: int
    cache_hit_rate: float
    model_family: str
    retention_mode: str
    ttl_seconds: float
    policy_reason: str
    policy_source_url: str
    retention_observation_state: RetentionObservationState
    retention_observation_reason: str
    observation_sample_source: RetentionObservationSampleSource
    observation_model_name: str
    observed_calls: int
    observed_input_tokens: int
    observed_cached_tokens: int
    observed_cache_hit_rate: float


@dataclass(frozen=True, slots=True)
class _CacheObservationSample:
    source: RetentionObservationSampleSource
    model_name: str
    calls: int
    input_tokens: int
    cached_tokens: int
    cache_hit_rate: float


def build_cache_health(message_stats: Mapping[str, object], *, model_name: str | None) -> CacheHealth:
    calls = _to_non_negative_int(message_stats.get("calls"))
    input_tokens = _to_non_negative_int(message_stats.get("inputTokens"))
    cached_tokens = _to_non_negative_int(message_stats.get("cachedTokens"))
    cache_hit_rate = _to_ratio(message_stats.get("cacheHitRate"))
    observation = _cache_observation_sample(message_stats, model_name)
    cache_policy = resolve_cache_ttl_prune_policy(model_name)
    retention_observation_state, retention_observation_reason = _build_retention_observation(
        calls=observation.calls,
        input_tokens=observation.input_tokens,
        cached_tokens=observation.cached_tokens,
    )

    active = (
        observation.calls >= _CACHE_ACTIVE_MIN_CALLS
        or observation.input_tokens >= _CACHE_ACTIVE_MIN_INPUT_TOKENS
        or observation.cached_tokens > 0
        or calls >= _CACHE_ACTIVE_MIN_CALLS
        or input_tokens >= _CACHE_ACTIVE_MIN_INPUT_TOKENS
        or cached_tokens > 0
    )
    if not active:
        status: HealthStatus = "inactive"
    elif observation.cache_hit_rate >= _CACHE_HEALTHY_HIT_RATE:
        status = "healthy"
    elif observation.cache_hit_rate >= _CACHE_WARNING_HIT_RATE or observation.cached_tokens >= _CACHE_ACTIVE_MIN_INPUT_TOKENS:
        status = "warning"
    else:
        status = "critical"

    return CacheHealth(
        status=status,
        active=active,
        calls=calls,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        cache_hit_rate=cache_hit_rate,
        model_family=cache_policy.model_family,
        retention_mode=cache_policy.reason,
        ttl_seconds=cache_policy.config.ttl_seconds,
        policy_reason=cache_policy.reason,
        policy_source_url=cache_policy.source_url,
        retention_observation_state=retention_observation_state,
        retention_observation_reason=retention_observation_reason,
        observation_sample_source=observation.source,
        observation_model_name=observation.model_name,
        observed_calls=observation.calls,
        observed_input_tokens=observation.input_tokens,
        observed_cached_tokens=observation.cached_tokens,
        observed_cache_hit_rate=observation.cache_hit_rate,
    )


def _cache_observation_sample(
    message_stats: Mapping[str, object],
    model_name: str | None,
) -> _CacheObservationSample:
    normalized_model_name = (model_name or "").strip()
    model_breakdown = message_stats.get("modelBreakdown")
    if normalized_model_name and isinstance(model_breakdown, Mapping):
        model_match = _matched_model_bucket(model_breakdown, normalized_model_name)
        if model_match is not None:
            matched_model_name, model_bucket = model_match
            model_calls = _to_non_negative_int(model_bucket.get("calls"))
            model_input_tokens = _to_non_negative_int(model_bucket.get("inputTokens"))
            model_cached_tokens = _to_non_negative_int(model_bucket.get("cachedTokens"))
            if model_calls > 0 or model_input_tokens > 0 or model_cached_tokens > 0:
                return _CacheObservationSample(
                    source="dominant_model",
                    model_name=matched_model_name,
                    calls=model_calls,
                    input_tokens=model_input_tokens,
                    cached_tokens=model_cached_tokens,
                    cache_hit_rate=model_cached_tokens / model_input_tokens if model_input_tokens > 0 else 0.0,
                )

    input_tokens = _to_non_negative_int(message_stats.get("inputTokens"))
    return _CacheObservationSample(
        source="session_aggregate",
        model_name="",
        calls=_to_non_negative_int(message_stats.get("calls")),
        input_tokens=input_tokens,
        cached_tokens=_to_non_negative_int(message_stats.get("cachedTokens")),
        cache_hit_rate=_to_ratio(message_stats.get("cacheHitRate")),
    )


def _matched_model_bucket(
    model_breakdown: Mapping[object, object],
    model_name: str,
) -> tuple[str, Mapping[str, object]] | None:
    exact_bucket = model_breakdown.get(model_name)
    if isinstance(exact_bucket, Mapping):
        return model_name, exact_bucket

    normalized_target = _normalized_model_key(model_name)
    if not normalized_target:
        return None

    matches: list[tuple[str, Mapping[str, object]]] = []
    for raw_key, raw_bucket in model_breakdown.items():
        if not isinstance(raw_key, str) or not isinstance(raw_bucket, Mapping):
            continue
        if _normalized_model_key(raw_key) == normalized_target:
            matches.append((raw_key, raw_bucket))
            if len(matches) > 1:
                return None
    return matches[0] if matches else None


def _normalized_model_key(model_name: str) -> str:
    normalized = model_name.strip().lower()
    for separator in ("/", ":"):
        prefix, found, suffix = normalized.partition(separator)
        if found and prefix in _MODEL_ROUTE_PREFIXES and suffix:
            return suffix.strip()
    return normalized


def _build_retention_observation(
    *,
    calls: int,
    input_tokens: int,
    cached_tokens: int,
) -> tuple[RetentionObservationState, str]:
    if calls < _CACHE_ACTIVE_MIN_CALLS and input_tokens < _CACHE_ACTIVE_MIN_INPUT_TOKENS and cached_tokens <= 0:
        return "insufficient_data", "insufficient usage sample for provider retention observation"
    if calls < _CACHE_ACTIVE_MIN_CALLS or input_tokens < _CACHE_ACTIVE_MIN_INPUT_TOKENS:
        return "insufficient_data", "sample below minimum calls or input tokens"
    if cached_tokens > 0:
        return "observed", "provider returned cached input tokens for this session"
    return "estimated", "static provider policy applies; no cached input tokens observed yet"


def _to_non_negative_int(value: object) -> int:
    return max(int(value), 0) if isinstance(value, (int, float)) else 0


def _to_ratio(value: object) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    numeric = float(value)
    if numeric < 0:
        return 0.0
    if numeric > 1:
        return 1.0
    return numeric


__all__ = [
    "CacheHealth",
    "RetentionObservationSampleSource",
    "RetentionObservationState",
    "build_cache_health",
]
