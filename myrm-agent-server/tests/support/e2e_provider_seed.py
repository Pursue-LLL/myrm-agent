"""Shared E2E provider-seed helpers for LIVE Chrome E2E tests.

Kept in tests/support so the failover and memory-AB disclosure E2E tests share
one upsert implementation — .env.test model/SSOT changes are applied in a
single place instead of drifting across duplicated copies.
"""

from __future__ import annotations

NONEXISTENT_MODEL_ID = "__e2e_nonexistent_model__"


def strip_provider_prefix(model: str) -> str:
    if "/" not in model:
        return model
    return model.split("/", 1)[1]


def infer_provider_id(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return "minimax"


def upsert_provider(
    providers: list[dict[str, object]],
    *,
    provider_id: str,
    model_id: str,
    api_url: str,
    api_key: str,
    merge_models: bool = False,
) -> list[dict[str, object]]:
    entry = {
        "id": provider_id,
        "name": provider_id,
        "apiUrl": api_url.rstrip("/"),
        "apiKeys": [{"key": api_key, "isActive": True}],
        "enabledModels": [model_id],
        "availableModels": [model_id],
        "providerType": "minimax" if provider_id == "minimax" else "openai",
        "isEnabled": True,
        "enabled": True,
    }
    merged: list[dict[str, object]] = []
    replaced = False
    for item in providers:
        if not isinstance(item, dict):
            continue
        if str(item.get("id")) == provider_id:
            if merge_models:
                enabled = item.get("enabledModels")
                available = item.get("availableModels")
                enabled_models = (
                    list(enabled) + [model_id]
                    if isinstance(enabled, list) and model_id not in enabled
                    else [model_id]
                )
                available_models = (
                    list(available) + [model_id]
                    if isinstance(available, list) and model_id not in available
                    else list(enabled_models)
                )
                entry = {
                    **entry,
                    "enabledModels": enabled_models,
                    "availableModels": available_models,
                }
            merged.append(entry)
            replaced = True
        else:
            merged.append(item)
    if not replaced:
        merged.append(entry)
    return merged
