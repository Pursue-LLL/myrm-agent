#!/usr/bin/env python3
"""Merge the community model price table into the bundled model catalog snapshot.

[INPUT]
- --source: URL or file path of ``model_prices_and_context_window.json`` (default: upstream main branch)
- the current snapshot (the merge baseline)

[OUTPUT]
- src/myrm_agent_harness/toolkits/llms/catalog/data/model_catalog.json (trimmed, sorted, compact JSON)
- a review report on stdout: models added, updated, kept although upstream dropped them, the keys whose window or
  price upstream no longer states, and the chat entries that state a price no token rate of the snapshot carries

[POS]
Maintainer tool: new models and price changes reach the product by re-running this script and committing the diff.
Only the modes and fields the product reads are kept, which keeps the snapshot a fraction of the upstream size; the
upstream ``litellm_provider`` field is stored as ``provider``. The request-shaping flags are among them
(``supports_sampling_params``, ``supports_adaptive_thinking``, ``supports_output_config``,
``supports_native_structured_output``, ``supports_parallel_tool_use_config`` and the
``supports_{none,xhigh,max}_reasoning_effort`` levels): the transport reads them to decide what a request may carry.
So are the prices by prompt size that models state as ``tiered_pricing`` rows (each row trimmed to its range and token
rates); a model priced only that way has no flat rate. A window stated as a whole float (``8192.0``) is stored as the
integer it is, the form every reader of the snapshot expects.

The merge is a union by key. A model upstream still lists takes upstream's whole entry (upstream corrects flags such as
``supports_reasoning``, so stale flags must not survive), a model upstream stopped listing keeps its last entry because
providers keep serving retired models for years and their window and price keep being read. Whether a model is gone is
the entry's own ``deprecation_date``. The script refuses an upstream that keeps fewer than half of the snapshot's keys,
which means a changed table format rather than a pruned table. A price shape the trimming does not keep would leave a
model silently unpriced, so the report counts, per provider, the chat entries upstream gives a price while the snapshot
holds no input and output token rate for them (priced per second or per character, say): a new family or a jump in the
count is a shape to teach the product.

Usage:
    uv run python scripts/sync_model_catalog.py [--source URL_OR_PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCE = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
OUTPUT = Path(__file__).resolve().parent.parent / "src/myrm_agent_harness/toolkits/llms/catalog/data/model_catalog.json"
MODES = frozenset({"chat", "completion", "responses", "embedding", "rerank", "image_generation", "image_edit"})
FIELDS = re.compile(
    r"^(?:litellm_provider|mode|max_tokens|max_input_tokens|max_output_tokens|output_vector_size|deprecation_date"
    r"|supports_(?:function_calling|vision|reasoning|prompt_caching|web_search|response_schema|tool_choice"
    r"|pdf_input|parallel_function_calling|system_messages|audio_input|video_input"
    r"|sampling_params|adaptive_thinking|output_config|native_structured_output|parallel_tool_use_config"
    r"|(?:none|xhigh|max)_reasoning_effort)"
    r"|(?:input|output)_cost_per_(?:token|image|query|pixel|second)(?:_above_\d+k?_tokens)?"
    r"|cache_(?:read|creation)_input_token_cost(?:_above_\d+k?_tokens)?"
    r"|search_context_cost_per_query|output_cost_per_reasoning_token|tiered_pricing)$"
)
# What a ``tiered_pricing`` row keeps: the prompt-size range it covers and the rates billed inside it.
TIER_FIELDS = frozenset(
    {
        "range",
        "input_cost_per_token",
        "output_cost_per_token",
        "output_cost_per_reasoning_token",
        "cache_read_input_token_cost",
        "cache_creation_input_token_cost",
    }
)
COUNT_FIELDS = frozenset({"max_tokens", "max_input_tokens", "max_output_tokens", "output_vector_size"})
CHAT_MODES = frozenset({"chat", "completion", "responses"})
PRICE_FIELD = re.compile(r"cost|pric")
TOKEN_RATES = ("input_cost_per_token", "output_cost_per_token")
# The facts every consumer reads; an upstream entry that stops stating one is listed for review, never patched.
KEY_FACTS = ("max_input_tokens", *TOKEN_RATES)
MIN_KEPT_KEY_RATIO = 0.5

Table = dict[str, dict[str, object]]


@dataclass(frozen=True)
class MergeResult:
    table: Table
    added: list[str]
    updated: list[str]
    retained: list[str]
    lost_facts: list[tuple[str, str]]


def _load(source: str) -> dict[str, object]:
    table: dict[str, object]
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as response:  # noqa: S310  # fixed https maintainer source
            table = json.load(response)
    else:
        table = json.loads(Path(source).read_text(encoding="utf-8"))
    return table


def _kept_value(field: str, value: object) -> object:
    if field in COUNT_FIELDS and isinstance(value, float) and value.is_integer():
        return int(value)
    if field == "tiered_pricing" and isinstance(value, list):
        return [
            {name: rate for name, rate in row.items() if name in TIER_FIELDS} for row in value if isinstance(row, dict)
        ]
    return value


def trim(table: Mapping[str, object]) -> Table:
    trimmed: Table = {}
    for key, entry in table.items():
        if key == "sample_spec" or not isinstance(entry, dict) or entry.get("mode") not in MODES:
            continue
        kept = {field: _kept_value(field, value) for field, value in entry.items() if FIELDS.match(field)}
        if "litellm_provider" in kept:
            kept["provider"] = kept.pop("litellm_provider")
        trimmed[key] = kept
    return trimmed


def _has_token_rates(entry: Mapping[str, object]) -> bool:
    """Whether the entry states an input and an output token rate, flat or in one of its price tiers."""
    rows = entry.get("tiered_pricing")
    priced = [entry, *(row for row in rows if isinstance(row, dict))] if isinstance(rows, list) else [entry]
    return any(all(rate in candidate for rate in TOKEN_RATES) for candidate in priced)


def _states_a_price(source: object) -> bool:
    return isinstance(source, dict) and any(PRICE_FIELD.search(field) for field in source)


def unreadable_prices(raw: Mapping[str, object], trimmed: Table) -> dict[str, int]:
    """Per provider: the chat entries upstream gives a price while the trimmed entry holds no token rates."""
    return dict(
        Counter(
            str(entry.get("provider", "unknown"))
            for key, entry in trimmed.items()
            if entry.get("mode") in CHAT_MODES and _states_a_price(raw[key]) and not _has_token_rates(entry)
        )
    )


def merge(snapshot: Table, upstream: Table) -> MergeResult:
    """Upstream's entry wins per key; keys only the snapshot has stay as they are."""
    added = sorted(upstream.keys() - snapshot.keys())
    retained = sorted(snapshot.keys() - upstream.keys())
    updated = sorted(key for key in upstream.keys() & snapshot.keys() if upstream[key] != snapshot[key])
    lost_facts = [
        (key, fact) for key in updated for fact in KEY_FACTS if fact in snapshot[key] and fact not in upstream[key]
    ]
    return MergeResult({**snapshot, **upstream}, added, updated, retained, lost_facts)


def _report(result: MergeResult, unreadable: Mapping[str, int]) -> str:
    lines = [
        f"added {len(result.added)}, updated {len(result.updated)}, "
        f"kept although upstream dropped them {len(result.retained)}, "
        f"entries that lost a window or price upstream {len(result.lost_facts)}"
    ]
    lines += [f"  lost {fact}: {key}" for key, fact in result.lost_facts]
    families = ", ".join(f"{provider} {count}" for provider, count in sorted(unreadable.items()))
    lines.append(f"chat entries with a price but no token rate: {sum(unreadable.values())} ({families or 'none'})")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="URL or path of the upstream JSON table")
    args = parser.parse_args()
    raw = _load(args.source)
    upstream = trim(raw)
    snapshot: Table = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    kept_keys = len(upstream.keys() & snapshot.keys())
    if not upstream or kept_keys < MIN_KEPT_KEY_RATIO * len(snapshot):
        print(
            f"Refusing to write: upstream lists {len(upstream)} models and keeps {kept_keys} of the snapshot's "
            f"{len(snapshot)} keys (the table format has probably changed)",
            file=sys.stderr,
        )
        return 1
    result = merge(snapshot, upstream)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result.table, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(_report(result, unreadable_prices(raw, upstream)))
    print(f"Wrote {len(result.table)} models to {OUTPUT} ({OUTPUT.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
