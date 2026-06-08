"""Provider credential lookup and legacy provider id normalization at the Agent HTTP boundary.

[INPUT]
- app.core.channel_bridge.model_resolver (POS: Business-layer model resolution; exposes `_extract_active_key` for enabled provider rows)

[OUTPUT]
- normalize_storage_provider_id: canonical storage id for inbound selections
- _find_provider_api_key: resolve secrets from enabled provider rows only (WebUI config)
- _resolve_image_api_key_provider: credential bucket id for image models
- `_camel_to_snake` / `_parse_camel_dict`: media param coercion helpers

[POS]
Aligns persisted frontend provider rows (`id`, `routingProfile`) with media/chat credential lookup.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel


def _legacy_remap_path() -> Path:
    for base in Path(__file__).resolve().parents:
        candidate = base / "shared" / "config" / "provider_legacy_remap.json"
        if candidate.is_file():
            return candidate
    msg = "provider_legacy_remap.json not found under shared/config/"
    raise FileNotFoundError(msg)


def _load_legacy_provider_remap() -> dict[str, str]:
    path = _legacy_remap_path()
    raw_obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_obj, dict):
        raise TypeError("provider_legacy_remap.json must contain a JSON object")
    result: dict[str, str] = {}
    for key_obj, val_obj in raw_obj.items():
        if not isinstance(key_obj, str) or not isinstance(val_obj, str):
            raise TypeError("provider_legacy_remap.json keys and values must be strings")
        result[key_obj] = val_obj
    return result


LEGACY_STORAGE_PROVIDER_ID_REMAP: dict[str, str] = _load_legacy_provider_remap()


def normalize_storage_provider_id(provider_id: str) -> str:
    """Map deprecated client/provider IDs to canonical storage IDs (same rules as frontend migration)."""
    key = provider_id.strip().replace("-", "_").lower()
    return LEGACY_STORAGE_PROVIDER_ID_REMAP.get(key, provider_id.strip())


def _provider_row_matches(normalized_provider_id: str, row: dict[str, object]) -> bool:
    pid = str(row.get("id", "")).replace("-", "_").lower()
    routing_raw = row.get("routingProfile")
    routing = str(routing_raw or "").replace("-", "_").lower()
    needle = normalized_provider_id.lower()
    return pid == needle or (routing != "" and routing == needle)


logger = logging.getLogger(__name__)


def _camel_to_snake(name: str) -> str:
    """Convert camelCase key to snake_case."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def _parse_camel_dict(raw: dict[str, object], model_cls: type[BaseModel]) -> dict[str, object]:
    """Convert camelCase dict keys to snake_case, filtering to valid model fields."""
    field_names = model_cls.model_fields.keys()
    return {_camel_to_snake(k): v for k, v in raw.items() if _camel_to_snake(k) in field_names}


def _find_provider_api_key(
    providers_dict: dict[str, object] | None,
    provider_id: str,
) -> str | None:
    """Resolve API key from enabled provider rows in WebUI config only."""

    slug = normalize_storage_provider_id(provider_id).replace("-", "_").lower()

    if not providers_dict:
        return None

    from app.core.channel_bridge.model_resolver import _extract_active_key

    providers = providers_dict.get("providers")
    if isinstance(providers, list):
        for p in providers:
            if not isinstance(p, dict) or not p.get("isEnabled"):
                continue
            if _provider_row_matches(slug, p):
                key = _extract_active_key(p)
                if key:
                    return key

    return None


def _resolve_image_api_key_provider(model: str) -> str:
    """Resolve which provider's API key to use for a given image model."""
    try:
        from myrm_agent_harness.toolkits.llms.image.types import get_profile

        profile = get_profile(model)
        if profile is not None:
            prov = getattr(profile, "api_key_provider", None)
            if isinstance(prov, str):
                return prov
    except ImportError:
        pass
    return "openai"
