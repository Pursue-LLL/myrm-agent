"""Net USD savings from prompt-cache reads, after the write premium.

[INPUT]
- toolkits.llms.catalog::model_info (POS: per-token input, cache-read and cache-write prices)
- usage mapping (prompt_tokens_details.cached_tokens / cache_creation_input_tokens, or flat cached_tokens)

[OUTPUT]
- calculate_cache_savings_usd: estimated net savings of the cache for one call

[POS]
Cache ROI figure for the usage report. A model whose catalog entry lists no cache-read price yields 0: a discount
the catalog does not declare is never assumed.
"""

from __future__ import annotations

from collections.abc import Mapping

from myrm_agent_harness.toolkits.llms.catalog import model_info


def _count(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _cache_tokens(usage: Mapping[str, object]) -> tuple[int, int]:
    """(cache-read tokens, cache-write tokens) from the nested details, falling back to the flat field."""
    details = usage.get("prompt_tokens_details")
    read = write = 0
    if isinstance(details, Mapping):
        read = _count(details.get("cached_tokens"))
        write = _count(details.get("cache_creation_input_tokens"))
    if not read and not write:
        read = _count(usage.get("cached_tokens"))
    return read, write


def _price(info: Mapping[str, object], key: str) -> float | None:
    value = info.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def calculate_cache_savings_usd(usage: Mapping[str, object], model: str | None) -> float:
    """Net savings in USD: read discount on cached tokens minus the premium paid to write the cache.

    Negative when the write premium exceeds the read savings.
    """
    if not model or not usage:
        return 0.0
    read_tokens, write_tokens = _cache_tokens(usage)
    if read_tokens <= 0 and write_tokens <= 0:
        return 0.0
    info = model_info(model)
    if info is None:
        return 0.0
    input_price = _price(info, "input_cost_per_token") or 0.0
    read_price = _price(info, "cache_read_input_token_cost")
    if read_price is None:
        return 0.0
    write_price = _price(info, "cache_creation_input_token_cost")
    write_premium = max(0.0, write_price - input_price) if write_price is not None else 0.0
    return read_tokens * (input_price - read_price) - write_tokens * write_premium
