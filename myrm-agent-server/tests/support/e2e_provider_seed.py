"""@input: urllib (stdlib), tests.support.test_secrets::TestSecrets (POS: [T] secrets loader)
@output: ResolvedE2ELlmEndpoints, resolve_e2e_llm_endpoints(), probe_openai_compatible_base(), probe_llm_api_key(), upsert_provider(), infer_provider_id(), strip_provider_prefix()
@pos: [T] Shared LIVE Chrome E2E provider-seed SSOT — single upsert + LLM endpoint resolve with OmniRoute gateway preflight (fail-fast, no silent fallback).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from tests.support.test_secrets import TestSecrets, load_test_secrets

NONEXISTENT_MODEL_ID = "__e2e_nonexistent_model__"
_LOCAL_GATEWAY_HOST = "localhost:20128"


@dataclass(frozen=True)
class ResolvedE2ELlmEndpoints:
    basic_base_url: str
    basic_model: str
    basic_api_key: str
    lite_base_url: str
    lite_model: str
    lite_api_key: str


def probe_openai_compatible_base(base_url: str, *, timeout_sec: float = 3.0) -> bool:
    """Return True when ``GET {base_url}/models`` responds with HTTP 200."""
    url = f"{base_url.rstrip('/')}/models"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return int(resp.status) == 200
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False


def _chat_probe_model(base_url: str, model: str) -> str:
    """Return model id for chat probe.

    OmniRoute combo mappings match full patterns (e.g. ``openai-like/agnes-2.5-flash``).
    Direct upstream APIs expect the bare model id after the provider prefix.
    """
    if _LOCAL_GATEWAY_HOST in base_url:
        return model
    return model.split("/", 1)[1] if "/" in model else model


def _chat_probe_max_tokens(base_url: str) -> int:
    """Reasoning models on OmniRoute combos need more than one output token."""
    return 16 if _LOCAL_GATEWAY_HOST in base_url else 1


def probe_llm_api_key(
    base_url: str,
    api_key: str,
    model: str,
    *,
    timeout_sec: float = 8.0,
) -> bool:
    """Return True when a minimal chat completion succeeds (auth + routing)."""
    model_id = _chat_probe_model(base_url, model)
    payload = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": _chat_probe_max_tokens(base_url),
        }
    ).encode("utf-8")
    url = f"{base_url.rstrip('/')}/chat/completions"
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return int(resp.status) == 200
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False


def resolve_e2e_llm_endpoints(
    secrets: TestSecrets | None = None,
) -> ResolvedE2ELlmEndpoints:
    """Resolve LIVE E2E LLM endpoints; fail fast when OmniRoute :20128 is misconfigured."""
    resolved = secrets or load_test_secrets()
    basic_url = resolved.basic_base_url
    lite_url = resolved.lite_base_url or basic_url
    basic_model = resolved.basic_model
    lite_model = resolved.lite_model or basic_model
    basic_key = resolved.basic_api_key
    lite_key = resolved.lite_api_key or basic_key

    uses_local_gateway = (
        _LOCAL_GATEWAY_HOST in basic_url or _LOCAL_GATEWAY_HOST in lite_url
    )
    if uses_local_gateway:
        gateway_reachable = probe_openai_compatible_base(basic_url)
        gateway_auth_ok = (
            probe_llm_api_key(basic_url, basic_key, basic_model)
            if gateway_reachable
            else False
        )
        if not gateway_reachable:
            raise RuntimeError(
                f"OmniRoute gateway {_LOCAL_GATEWAY_HOST} unreachable — "
                "start with: bash ~/.omniroute/start-omniroute.sh"
            )
        if not gateway_auth_ok:
            raise RuntimeError(
                f"OmniRoute gateway {_LOCAL_GATEWAY_HOST} rejected BASIC_API_KEY or "
                f"BASIC_MODEL ({basic_model!r}) on chat preflight — fix .env.test"
            )

    return ResolvedE2ELlmEndpoints(
        basic_base_url=basic_url,
        basic_model=basic_model,
        basic_api_key=basic_key,
        lite_base_url=lite_url,
        lite_model=lite_model,
        lite_api_key=lite_key,
    )


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


def build_e2e_model_selection(*, use_lite: bool = True) -> dict[str, object]:
    """Model selection for LIVE agent-stream using gateway preflight."""
    from tests.api.agent.utils import _convert_litellm_model

    endpoints = resolve_e2e_llm_endpoints()
    raw_model = endpoints.lite_model if use_lite else endpoints.basic_model
    base_url = endpoints.lite_base_url if use_lite else endpoints.basic_base_url
    return {
        "providerId": infer_provider_id(raw_model),
        "model": _convert_litellm_model(raw_model),
        "baseUrl": base_url,
    }


def seed_live_e2e_providers(api_url: str) -> ResolvedE2ELlmEndpoints:
    """Seed WebUI providers/defaultModelConfig for LIVE SHPOIB with working LLM endpoints."""
    from cdp_chat.support import fetch_config_value, put_config_value

    endpoints = resolve_e2e_llm_endpoints()
    basic_provider_id = infer_provider_id(endpoints.basic_model)
    lite_provider_id = infer_provider_id(endpoints.lite_model)
    basic_model_id = strip_provider_prefix(endpoints.basic_model)
    lite_model_id = strip_provider_prefix(endpoints.lite_model)

    current = fetch_config_value("providers", api_url=api_url)
    provider_list = current.get("providers")
    providers = provider_list if isinstance(provider_list, list) else []
    providers = upsert_provider(
        [p for p in providers if isinstance(p, dict)],
        provider_id=basic_provider_id,
        model_id=basic_model_id,
        api_url=endpoints.basic_base_url,
        api_key=endpoints.basic_api_key,
    )
    providers = upsert_provider(
        providers,
        provider_id=lite_provider_id,
        model_id=lite_model_id,
        api_url=endpoints.lite_base_url,
        api_key=endpoints.lite_api_key,
        merge_models=True,
    )

    dmc = dict(current.get("defaultModelConfig") or {})
    base_primary = {"providerId": basic_provider_id, "model": basic_model_id}
    lite_primary = {"providerId": lite_provider_id, "model": lite_model_id}
    dmc["baseModel"] = {
        "primary": base_primary,
        "fallback": dict(lite_primary),
        "temperature": 0.7,
        "modelKwargs": {},
    }
    dmc["liteModel"] = {
        "primary": dict(lite_primary),
        "fallback": dict(base_primary),
        "temperature": 0.7,
    }

    merged: dict[str, object] = {
        **current,
        "providers": providers,
        "defaultModelConfig": dmc,
        "customModelInfo": current.get("customModelInfo") or {},
    }
    put_config_value("providers", merged, api_url=api_url)
    return endpoints
