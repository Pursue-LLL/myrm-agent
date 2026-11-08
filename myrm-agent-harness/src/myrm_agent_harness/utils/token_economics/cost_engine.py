"""Cost computation engine with provenance tracking and cache-aware pricing.

[INPUT]
- toolkits.llms.catalog::cost_per_token (POS: cache-aware pricing from the model catalog)
- model / prompt_tokens / completion_tokens / cache_read_tokens / cache_write_tokens

[OUTPUT]
- CostStatus: Cost provenance enum (actual / estimated / unknown)
- CostResult: Computed cost in USD with provenance status
- compute_cost_by_tokens(): Cache-aware cost from token counts

[POS]
Token-economics core of the framework. A model the catalog prices under its own provider is billed as ``ACTUAL``;
a gateway-qualified name (``my-gateway/gpt-4o``) that only resolves once the gateway segment is stripped is billed
as ``ESTIMATED`` so a borrowed price is never presented as the vendor's own. An unpriced model is ``UNKNOWN``, never
zero, so a missing price cannot pass for a free call.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from myrm_agent_harness.toolkits.llms.catalog import cost_per_token


class CostStatus(StrEnum):
    """Cost provenance — how the cost figure was obtained."""

    ACTUAL = "actual"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CostResult:
    """Computed cost in USD with provenance."""

    usd: float = 0.0
    status: CostStatus = CostStatus.UNKNOWN

    @property
    def is_known(self) -> bool:
        return self.status != CostStatus.UNKNOWN


def _priced(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    provider: str | None,
) -> float:
    """Total USD for the model, or 0.0 when the catalog has no price for it."""
    costs = cost_per_token(
        model,
        prompt_tokens,
        completion_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        provider=provider,
    )
    return 0.0 if costs is None else costs[0] + costs[1]


def compute_cost_by_tokens(
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    custom_llm_provider: str | None = None,
    request_model: str | None = None,
) -> CostResult:
    """Cache-aware cost from token counts; ``prompt_tokens`` includes the cached tokens."""
    target = (request_model or model or "").strip()
    if not target or (prompt_tokens <= 0 and completion_tokens <= 0):
        return CostResult()

    usd = _priced(target, prompt_tokens, completion_tokens, cache_read_tokens, cache_write_tokens, custom_llm_provider)
    if usd > 0:
        return CostResult(usd=usd, status=CostStatus.ACTUAL)

    _, separator, remainder = target.partition("/")
    if separator:
        usd = _priced(remainder, prompt_tokens, completion_tokens, cache_read_tokens, cache_write_tokens, None)
        if usd > 0:
            return CostResult(usd=usd, status=CostStatus.ESTIMATED)
    return CostResult()


__all__ = [
    "CostResult",
    "CostStatus",
    "compute_cost_by_tokens",
]
