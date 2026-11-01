# catalog/

## Overview

Model catalog: context windows, output ceilings, per-token prices and capability flags per model. The data is a trimmed
snapshot of the community-maintained model price table, bundled with the package and loaded once on first use;
`scripts/sync_model_catalog.py` refreshes it from upstream. Runtime registrations (user-defined models, corrected prices)
sit on top of the snapshot.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Exports `model_info`, `register_model`, `known_models`, `cost_per_token`, `supports_web_search` | — |
| `store.py` | Core | Snapshot loading, runtime registrations, lookup: an exact key wins, otherwise provider-strict (`provider/model` never resolves to another provider's entry) | ✅ |
| `pricing.py` | Core | `cost_per_token`: cache-aware cost (own rates for cache reads and writes, higher tier above 200k prompt tokens), `None` for an unpriced model | ✅ |
| `data/model_catalog.json` | Data | The bundled snapshot; every entry names its owning provider under `provider` | — |

## Key Dependencies

- Consumed by `utils/token_economics` (cost and cache savings), `toolkits/llms/core/llm.py` and `toolkits/llms/utils/model_utils.py` (limits, native
  search), `toolkits/llms/adapters/wire/routing.py` (responses-only models) and the server model-listing and pricing APIs
