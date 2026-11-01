#!/usr/bin/env python3
"""Refresh the bundled model catalog snapshot from the community model price table.

[INPUT]
- --source: URL or file path of ``model_prices_and_context_window.json`` (default: upstream main branch)

[OUTPUT]
- src/myrm_agent_harness/toolkits/llms/catalog/data/model_catalog.json (trimmed, sorted, compact JSON)

[POS]
Maintainer tool: new models and price changes reach the product by re-running this script and committing the diff.
Only the modes and fields the product reads are kept, which keeps the snapshot a fraction of the upstream size; the
upstream ``litellm_provider`` field is stored as ``provider``.

Usage:
    uv run python scripts/sync_model_catalog.py [--source URL_OR_PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

DEFAULT_SOURCE = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "src/myrm_agent_harness/toolkits/llms/catalog/data/model_catalog.json"
)
MODES = frozenset({"chat", "completion", "responses", "embedding", "rerank", "image_generation", "image_edit"})
FIELDS = re.compile(
    r"^(?:litellm_provider|mode|max_tokens|max_input_tokens|max_output_tokens|output_vector_size|deprecation_date"
    r"|supports_(?:function_calling|vision|reasoning|prompt_caching|web_search|response_schema|tool_choice"
    r"|pdf_input|parallel_function_calling|system_messages|audio_input|video_input)"
    r"|(?:input|output)_cost_per_(?:token|image|query|pixel|second)(?:_above_\d+k?_tokens)?"
    r"|cache_(?:read|creation)_input_token_cost(?:_above_\d+k?_tokens)?"
    r"|search_context_cost_per_query|output_cost_per_reasoning_token)$"
)


def _load(source: str) -> dict[str, object]:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as response:  # noqa: S310  # fixed https maintainer source
            return json.load(response)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def trim(table: dict[str, object]) -> dict[str, dict[str, object]]:
    trimmed: dict[str, dict[str, object]] = {}
    for key, entry in table.items():
        if key == "sample_spec" or not isinstance(entry, dict) or entry.get("mode") not in MODES:
            continue
        kept = {field: value for field, value in entry.items() if FIELDS.match(field)}
        if "litellm_provider" in kept:
            kept["provider"] = kept.pop("litellm_provider")
        trimmed[key] = kept
    return trimmed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="URL or path of the upstream JSON table")
    args = parser.parse_args()
    trimmed = trim(_load(args.source))
    if len(trimmed) < 1000:
        print(f"Refusing to write: only {len(trimmed)} entries survived trimming (expected thousands)", file=sys.stderr)
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(trimmed, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(trimmed)} models to {OUTPUT} ({OUTPUT.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
