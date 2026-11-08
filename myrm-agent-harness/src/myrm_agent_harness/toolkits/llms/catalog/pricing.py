"""Token cost computation from catalog prices.

[INPUT]
- catalog.store (POS: model_info — per-token prices and prompt-size price tiers)

[OUTPUT]
- cost_per_token: (prompt_cost, completion_cost) in USD for one call's token counts, or None for an unpriced model

[POS]
Cache-aware pricing shared by the cost engine and the savings report. ``prompt_tokens`` is the total prompt size
including cached tokens (the shape every transport wire reports); cache reads and writes are billed at their own
rates and the rest at the input rate. Models that price long prompts higher switch every rate once the prompt
crosses a threshold, either as flat ``*_above_200k_tokens`` rates or as ``tiered_pricing`` rows; in both the whole
request, completion included, is billed at the tier the prompt size falls in (a row covers up to and including its
upper bound, a prompt beyond the last bound takes the last row), as the providers bill it. A row carries every rate
of its tier, so nothing is borrowed from the entry's flat rates. A cache price the catalog does not list is billed at
the input rate instead of free, so an unlisted discount never understates a bill.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.toolkits.llms.catalog.store import ModelInfo, model_info

_TIER_KEY: Final = re.compile(r"^input_cost_per_token_above_(\d+)(k?)_tokens$")


def _rate(info: ModelInfo, key: str, tier: str = "") -> float | None:
    value = info.get(f"{key}{tier}", info.get(key))
    return float(value) if isinstance(value, (int, float)) else None


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tiers(info: ModelInfo) -> list[tuple[float, Mapping[str, object]]]:
    """(upper bound, rates) of the usable ``tiered_pricing`` rows, ascending.

    A row lacking its upper bound or an input or output token rate is skipped.
    """
    rows = info.get("tiered_pricing")
    tiers: list[tuple[float, Mapping[str, object]]] = []
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        bounds = row.get("range")
        if (
            isinstance(bounds, list)
            and len(bounds) == 2
            and _number(bounds[1])
            and _number(row.get("input_cost_per_token"))
            and _number(row.get("output_cost_per_token"))
        ):
            tiers.append((float(bounds[1]), row))
    return sorted(tiers, key=lambda tier: tier[0])


def _tier_suffix(info: Mapping[str, object], prompt_tokens: int) -> str:
    """Suffix of the highest price tier the prompt size crosses ('' when none)."""
    best_threshold, best_suffix = -1, ""
    for key in info:
        match = _TIER_KEY.match(key)
        if match is None:
            continue
        threshold = int(match[1]) * (1000 if match[2] else 1)
        if prompt_tokens > threshold > best_threshold:
            best_threshold, best_suffix = threshold, key.removeprefix("input_cost_per_token")
    return best_suffix


def _rates_for(info: ModelInfo, prompt_tokens: int) -> tuple[ModelInfo, str]:
    """The rates billing a prompt of this size, and the suffix of their keys.

    A ``tiered_pricing`` row when the entry has usable ones, else the entry itself.
    """
    tiers = _tiers(info)
    if not tiers:
        return info, _tier_suffix(info, prompt_tokens)
    return next((rates for bound, rates in tiers if prompt_tokens <= bound), tiers[-1][1]), ""


def cost_per_token(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    provider: str | None = None,
) -> tuple[float, float] | None:
    info = model_info(model, provider)
    if info is None:
        return None
    rates, tier = _rates_for(info, prompt_tokens)
    input_rate = _rate(rates, "input_cost_per_token", tier)
    output_rate = _rate(rates, "output_cost_per_token", tier)
    if input_rate is None or output_rate is None:
        return None
    read_rate = _rate(rates, "cache_read_input_token_cost", tier)
    write_rate = _rate(rates, "cache_creation_input_token_cost", tier)
    cached = max(0, min(cache_read_tokens, prompt_tokens))
    written = max(0, min(cache_write_tokens, prompt_tokens - cached))
    fresh = max(0, prompt_tokens) - cached - written
    prompt_cost = (
        fresh * input_rate
        + cached * (input_rate if read_rate is None else read_rate)
        + written * (input_rate if write_rate is None else write_rate)
    )
    return prompt_cost, max(0, completion_tokens) * output_rate
