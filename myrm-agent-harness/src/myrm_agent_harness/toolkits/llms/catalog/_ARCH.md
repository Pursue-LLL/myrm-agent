# catalog/

## Overview

Model catalog: context windows, output ceilings, per-token prices (flat, or by prompt size as `tiered_pricing` rows) and capability flags per model, including the flags that
shape a request (sampling parameters, adaptive thinking, `none`/`xhigh`/`max` reasoning effort, native structured output and
`disable_parallel_tool_use` on Bedrock). The data is a trimmed
snapshot of the community-maintained model price table, bundled with the package and loaded once on first use;
`scripts/sync_model_catalog.py` merges upstream into it (a union by key: a model upstream stops listing stays, because
providers keep serving it; the price tiers and the integer windows survive the trimming, and the report counts the chat entries
that state a price no token rate of the snapshot carries). Runtime registrations (user-defined models, corrected prices) overlay the snapshot entry the
id resolves to: limits and flags carry over, stated prices replace the whole price group.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Exports `model_info`, `model_facts`, `register_model`, `known_models`, `is_deprecated`, `cost_per_token`, `supports_web_search` | — |
| `store.py` | Core | Snapshot loading, runtime registrations, lookup: case-insensitive, an exact spelling wins, otherwise provider-strict (`provider/model` never resolves to another provider's entry); `model_facts` widens it for window/flag questions by dropping gateway segments; `register_model` overlays; `is_deprecated` reads `deprecation_date` | ✅ |
| `pricing.py` | Core | `cost_per_token`: cache-aware cost (own rates for cache reads and writes); the whole request is billed at the tier its prompt size falls in, whether the entry states it as `tiered_pricing` rows or as flat `*_above_200k_tokens` rates; `None` for an unpriced model | ✅ |
| `data/model_catalog.json` | Data | The bundled snapshot; every entry names its owning provider under `provider`; windows and vector sizes are integers | — |

## Key Dependencies

- Consumed by `utils/token_economics` (cost and cache savings), `toolkits/llms/core/llm.py` and `toolkits/llms/utils/model_utils.py` (limits, native
  search), `toolkits/llms/transport/capabilities.py` (request-shaping flags), `toolkits/llms/adapters/wire/routing.py` (responses-only models) and the server model-listing and pricing APIs

## Constraints

- A prompt-size tier bills the whole request, completion included, at the tier the prompt falls in: a row covers up to and
  including its upper bound and a prompt beyond the last bound takes the last row, as the providers publish it. A row carries
  every rate of its tier, so no rate is borrowed from the entry's flat prices. Pinned by `test_pricing_tiers.py`.
- A model priced only by tiers (`dashscope`, `qwencloud`, `qwen_ai_platform`, `volcengine`) carries no flat price:
  `cost_per_token` prices it, while the readers of flat fields (the server's model-pricing listing, the cache-savings
  report) show nothing for it. The snapshot test fails when a sync leaves such a model unpriced.
- A registration that states a price (flat or `tiered_pricing`) replaces the whole price group of the entry it overlays.
- A window or a vector size is an `int` in the snapshot, because every reader treats a float as no value.
