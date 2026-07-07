"""Consolidate split providers config keys into the canonical `providers` bundle.

Legacy rows stored `defaultModelConfig` and `customModelInfo` as separate UserConfig
entries while the frontend syncs a single `providers` bundle. This migration merges
standalone rows into `providers` and deletes the split keys.

[INPUT]
- app.services.config.service::config_service

[OUTPUT]
- consolidate_split_providers_keys: merge split keys into providers bundle

[POS]
Startup migration for legacy provider config rows. Runs once per server boot.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.config.service import config_service

logger = logging.getLogger(__name__)

_SPLIT_KEYS = ("defaultModelConfig", "customModelInfo")
_CONSOLIDATION_DEVICE = "config-key-consolidation"


def _as_dict(raw: object) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


def _values_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


async def consolidate_split_providers_keys() -> dict[str, int]:
    """Merge standalone provider sub-keys into `providers` and delete legacy rows."""
    stats = {"merged": 0, "deleted": 0, "skipped": 0}

    split_records = [await config_service.get(key) for key in _SPLIT_KEYS]
    if not any(record is not None for record in split_records):
        stats["skipped"] = 1
        return stats

    providers_record = await config_service.get("providers")
    providers_value: dict[str, Any] = _as_dict(providers_record.value if providers_record else None)
    original_providers = dict(providers_value)

    for key, record in zip(_SPLIT_KEYS, split_records, strict=True):
        if record is None:
            continue
        split_value = _as_dict(record.value)
        if split_value and providers_value.get(key) != split_value:
            providers_value[key] = split_value

    if not _values_equal(original_providers, providers_value):
        await config_service.set(
            config_key="providers",
            value=providers_value,
            device_id=_CONSOLIDATION_DEVICE,
        )
        stats["merged"] = 1

    for key, record in zip(_SPLIT_KEYS, split_records, strict=True):
        if record is None:
            continue
        deleted = await config_service.delete(key)
        if deleted:
            stats["deleted"] += 1

    if stats["merged"] or stats["deleted"]:
        logger.info("Consolidated split providers config keys: %s", stats)
    else:
        logger.debug("No split providers keys to consolidate")

    return stats
