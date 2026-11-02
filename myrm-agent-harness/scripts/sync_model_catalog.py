#!/usr/bin/env python3
"""Merge the community model price table into the bundled model catalog snapshot.

[INPUT]
- --source: URL or file path of ``model_prices_and_context_window.json`` (default: upstream main branch)
- the current snapshot (the merge baseline)

[OUTPUT]
- src/myrm_agent_harness/toolkits/llms/catalog/data/model_catalog.json (trimmed, sorted, compact JSON)
- a review report on stdout: models added, updated, kept although upstream dropped them, and the keys whose window or
  price upstream no longer states

[POS]
Maintainer tool: new models and price changes reach the product by re-running this script and committing the diff.
Only the modes and fields the product reads are kept, which keeps the snapshot a fraction of the upstream size; the
upstream ``litellm_provider`` field is stored as ``provider``.

The merge is a union by key. A model upstream still lists takes upstream's whole entry (upstream corrects flags such as
``supports_reasoning``, so stale flags must not survive), a model upstream stopped listing keeps its last entry because
providers keep serving retired models for years and their window and price keep being read. Whether a model is gone is
the entry's own ``deprecation_date``. The script refuses an upstream that keeps fewer than half of the snapshot's keys,
which means a changed table format rather than a pruned table.

Usage:
    uv run python scripts/sync_model_catalog.py [--source URL_OR_PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCE = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
OUTPUT = Path(__file__).resolve().parent.parent / "src/myrm_agent_harness/toolkits/llms/catalog/data/model_catalog.json"
MODES = frozenset({"chat", "completion", "responses", "embedding", "rerank", "image_generation", "image_edit"})
FIELDS = re.compile(
    r"^(?:litellm_provider|mode|max_tokens|max_input_tokens|max_output_tokens|output_vector_size|deprecation_date"
    r"|supports_(?:function_calling|vision|reasoning|prompt_caching|web_search|response_schema|tool_choice"
    r"|pdf_input|parallel_function_calling|system_messages|audio_input|video_input)"
    r"|(?:input|output)_cost_per_(?:token|image|query|pixel|second)(?:_above_\d+k?_tokens)?"
    r"|cache_(?:read|creation)_input_token_cost(?:_above_\d+k?_tokens)?"
    r"|search_context_cost_per_query|output_cost_per_reasoning_token)$"
)
# The facts every consumer reads; an upstream entry that stops stating one is listed for review, never patched.
KEY_FACTS = ("max_input_tokens", "input_cost_per_token", "output_cost_per_token")
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
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as response:  # noqa: S310  # fixed https maintainer source
            return json.load(response)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def trim(table: Mapping[str, object]) -> Table:
    trimmed: Table = {}
    for key, entry in table.items():
        if key == "sample_spec" or not isinstance(entry, dict) or entry.get("mode") not in MODES:
            continue
        kept = {field: value for field, value in entry.items() if FIELDS.match(field)}
        if "litellm_provider" in kept:
            kept["provider"] = kept.pop("litellm_provider")
        trimmed[key] = kept
    return trimmed


def merge(snapshot: Table, upstream: Table) -> MergeResult:
    """Upstream's entry wins per key; keys only the snapshot has stay as they are."""
    added = sorted(upstream.keys() - snapshot.keys())
    retained = sorted(snapshot.keys() - upstream.keys())
    updated = sorted(key for key in upstream.keys() & snapshot.keys() if upstream[key] != snapshot[key])
    lost_facts = [
        (key, fact) for key in updated for fact in KEY_FACTS if fact in snapshot[key] and fact not in upstream[key]
    ]
    return MergeResult({**snapshot, **upstream}, added, updated, retained, lost_facts)


def _report(result: MergeResult) -> str:
    lines = [
        f"added {len(result.added)}, updated {len(result.updated)}, "
        f"kept although upstream dropped them {len(result.retained)}, "
        f"entries that lost a window or price upstream {len(result.lost_facts)}"
    ]
    lines += [f"  lost {fact}: {key}" for key, fact in result.lost_facts]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="URL or path of the upstream JSON table")
    args = parser.parse_args()
    upstream = trim(_load(args.source))
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
    print(_report(result))
    print(f"Wrote {len(result.table)} models to {OUTPUT} ({OUTPUT.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
