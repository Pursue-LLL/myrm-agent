"""[INPUT]
- myrm_agent_harness.agent.config.parsers (POS: provider/model name conversion)

[OUTPUT]
- header builders, key extraction, name conversion/normalisation and the provider type map

[POS]
Model resolver shared primitives: header building, provider key discovery and provider/model naming.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse

from myrm_agent_harness.agent.config.parsers import parse_route_model_id, to_route_model_id

if TYPE_CHECKING:
    pass

_PROVIDER_API_BASES: dict[str, str] = {
    "siliconflow": "https://api.siliconflow.cn/v1",
}


_LOCAL_NO_AUTH_API_KEY_MARKER = "__myrm_local_no_auth__"


_PLATFORM_MANAGED_KEY = "platform-managed"


_OPENAI_LIKE_TYPES = {"openai-like", "openai_compatible", "openai-compatible", "openai_like"}


def _build_platform_headers(api_key: str) -> dict[str, object] | None:
    """Build transport header overrides for special credential markers.

    The relay requires X-Sandbox-Id and X-Telemetry-Token to authenticate
    requests that carry the "platform-managed" placeholder instead of a virtual key.
    """
    if api_key == _LOCAL_NO_AUTH_API_KEY_MARKER:
        # Keep synthetic marker for resolver bookkeeping but avoid forcing an
        # Authorization bearer token for local no-auth OpenAI-compatible endpoints.
        return {"extra_headers": {"Authorization": ""}}
    if api_key != _PLATFORM_MANAGED_KEY:
        return None
    from app.config.settings import settings

    cp = settings.control_plane
    sandbox_id = cp.sandbox_id
    token = cp.telemetry_token.get_secret_value()
    if not sandbox_id or not token:
        return None
    return {"extra_headers": {"X-Sandbox-Id": sandbox_id, "X-Telemetry-Token": token}}


def _build_transport_headers(
    api_key: str,
    provider_id: str = "",
    api_url: str | None = None,
) -> dict[str, object] | None:
    """Build transport header overrides including platform relay and gateway attribution."""
    headers: dict[str, str] = {}
    platform_override = _build_platform_headers(api_key)
    if platform_override and isinstance(platform_override.get("extra_headers"), dict):
        for k, v in platform_override["extra_headers"].items():
            if isinstance(v, str):
                headers[k] = v

    is_vercel_gateway = provider_id == "vercel_ai_gateway" or (api_url is not None and "ai-gateway.vercel.sh" in api_url.lower())
    if is_vercel_gateway:
        headers.setdefault("HTTP-Referer", "https://myrm.ai")
        headers.setdefault("X-Title", "Myrm Agent")

    return {"extra_headers": headers} if headers else None


def _parse_route_model_id(model_name: str) -> tuple[str, str]:
    """Parse a routed model name (wrapper for framework-level parser)."""
    return cast(tuple[str, str], parse_route_model_id(model_name))


def _to_route_model_id(provider: str, model: str, provider_type: str | None = None) -> str:
    """Convert provider + model to the routed form (wrapper for framework-level converter)."""
    if provider == "vercel_ai_gateway":
        clean_model = model.removeprefix("vercel_ai_gateway/")
        if clean_model.startswith("openai/"):
            return clean_model
        return f"openai/{clean_model}"
    return str(to_route_model_id(provider, model, provider_type))


def _extract_active_key(provider: dict[str, object]) -> str | None:
    """Extract the first active API key from a provider config dict."""
    keys = _extract_all_active_keys(provider)
    return keys[0] if keys else None


def _extract_all_active_keys(provider: dict[str, object]) -> list[str]:
    """Extract all active API keys from a provider config dict.

    Returns a list of active keys (may be empty). Used by credential pool
    for key rotation on rate-limit errors.

    Priority: explicit API keys > injected OAuth token > no-auth marker.
    """
    raw: object = provider.get("apiKeys")
    if not isinstance(raw, list):
        alt = provider.get("api_keys")
        raw = alt if isinstance(alt, list) else None
    if not isinstance(raw, list):
        raw = []
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        active = entry.get("isActive")
        if active is None:
            active = entry.get("is_active")
        key_raw = entry.get("key")
        if active and key_raw is not None:
            out.append(str(key_raw))
    if out:
        return out

    # Fallback to OAuth token injected by config_loader from provider_oauth credentials
    oauth_token = provider.get("_oauthToken")
    if isinstance(oauth_token, str) and oauth_token:
        return [oauth_token]

    if _supports_provider_no_auth(provider):
        return [_LOCAL_NO_AUTH_API_KEY_MARKER]
    return []


def _supports_provider_no_auth(provider: dict[str, object]) -> bool:
    provider_id = str(provider.get("id", "")).strip().lower()
    if provider_id in {"ollama", "lm_studio"}:
        return True
    provider_type = str(provider.get("providerType", "")).strip().lower()
    if provider_type not in _OPENAI_LIKE_TYPES:
        return False
    api_url = str(provider.get("apiUrl") or provider.get("baseURL") or "").strip()
    return _is_loopback_api_url(api_url)


def _is_loopback_api_url(api_url: str) -> bool:
    if not api_url:
        return False
    candidate = api_url if "://" in api_url else f"http://{api_url}"
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").strip().lower()
    if hostname == "localhost":
        return True
    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return ip_obj.is_loopback or ip_obj.is_unspecified


def _collapse_repeated_prefixes(model: str) -> str:
    """Collapse consecutively duplicated or alias-equivalent provider prefixes.

    e.g. 'anthropic/anthropic/claude-3-5-sonnet' -> 'anthropic/claude-3-5-sonnet'
         'openai_compatible/openai/deepseek-chat' -> 'openai_compatible/deepseek-chat'
    """
    parts = model.split("/")
    if len(parts) <= 1:
        return model

    alias_map = {
        "openai_compatible": "openai",
        "openai_like": "openai",
        "siliconflow": "openai",
        "anthropic_compatible": "anthropic",
        "anthropic_like": "anthropic",
        "gemini_compatible": "gemini",
        "gemini_like": "gemini",
    }

    collapsed: list[str] = [parts[0]]
    for part in parts[1:]:
        prev_canonical = collapsed[-1].lower().replace("-", "_")
        curr_canonical = part.lower().replace("-", "_")
        prev_family = alias_map.get(prev_canonical, prev_canonical)
        curr_family = alias_map.get(curr_canonical, curr_canonical)

        # Collapse if adjacent segments resolve to the same family and we are at prefix position
        if prev_family == curr_family and len(collapsed) == 1:
            continue
        collapsed.append(part)

    return "/".join(collapsed)


def _normalize_model_name(model: str) -> str:
    """Normalize model name to the routed format and collapse repeated prefixes.

    Converts legacy/alternative provider prefixes to the standard routed format:
    - openai-compatible/ -> openai/
    - openai_compatible/ -> openai/
    - gemini-compatible/ -> gemini/
    - anthropic-compatible/ -> anthropic/
    Also idempotently eliminates nested/duplicated prefixes (e.g. anthropic/anthropic/xxx -> anthropic/xxx).

    Args:
        model: Raw model name from config (e.g., "openai-compatible/deepseek-v4-flash")

    Returns:
        Normalized model name (e.g., "openai/deepseek-v4-flash")
    """
    import re

    cleaned = re.sub(r"/+", "/", model.strip())
    if "/" not in cleaned:
        return cleaned

    cleaned = _collapse_repeated_prefixes(cleaned)
    if "/" not in cleaned:
        return cleaned

    prefix, model_name = cleaned.split("/", 1)
    prefix_lower = prefix.lower().replace("-", "_")

    if prefix_lower in ("openai_compatible", "openai_like", "siliconflow"):
        prefix = "openai"
    elif prefix_lower in ("gemini_compatible", "gemini_like"):
        prefix = "gemini"
    elif prefix_lower in ("anthropic_compatible", "anthropic_like"):
        prefix = "anthropic"
    elif prefix_lower == "minimax":
        prefix = "minimax"
    elif prefix_lower == "xiaomi":
        prefix = "xiaomi_mimo"
    elif prefix_lower == "xiaomi_mimo":
        prefix = "xiaomi_mimo"

    # Multi-level prefix idempotent folding to catch e.g. anthropic/anthropic/xxx
    while "/" in model_name:
        sub_prefix, sub_model = model_name.split("/", 1)
        if sub_prefix.lower().replace("-", "_") in (prefix.lower().replace("-", "_"), prefix_lower):
            model_name = sub_model
        else:
            break

    return f"{prefix}/{model_name}" if prefix != model_name else model_name


def _build_provider_type_map(
    providers_dict: dict[str, object],
) -> dict[str, str | None]:
    """Build {provider_id: providerType} map from providers list."""
    providers = providers_dict.get("providers")
    if not isinstance(providers, list):
        return {}
    result: dict[str, str | None] = {}
    for p in providers:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", ""))
        ptype = str(p.get("providerType", "")) or None
        if pid:
            result[pid] = ptype
    return result
