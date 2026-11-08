"""Model catalog: context windows, output ceilings, prices and capability flags per model.

[INPUT]
- catalog.store (POS: bundled snapshot, runtime registrations, lookup)
- catalog.pricing (POS: cache-aware token pricing)

[OUTPUT]
- ModelInfo / model_info / model_facts / register_model / known_models / is_deprecated: catalog entries
- cost_per_token: USD cost of one call's token counts
- supports_web_search: whether the model offers a provider-native search tool

[POS]
The single price and capability table of the harness. The data is a trimmed snapshot of the community-maintained table; ``scripts/sync_model_catalog.py`` merges
upstream into it, so new models and price changes arrive by re-syncing, not by hand edits, and a model upstream stops listing stays.
"""

from myrm_agent_harness.toolkits.llms.catalog.pricing import cost_per_token
from myrm_agent_harness.toolkits.llms.catalog.store import (
    ModelInfo,
    is_deprecated,
    known_models,
    model_facts,
    model_info,
    register_model,
)


def supports_web_search(model: str, provider: str | None = None) -> bool:
    info = model_info(model, provider)
    return bool(info and info.get("supports_web_search") is True)


__all__ = [
    "ModelInfo",
    "cost_per_token",
    "is_deprecated",
    "known_models",
    "model_facts",
    "model_info",
    "register_model",
    "supports_web_search",
]
