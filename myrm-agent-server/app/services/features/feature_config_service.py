"""Feature configuration persistence — stores user feature overrides as JSON file.

Provides CRUD operations for user feature flag overrides.
Uses atomic write (tmp + os.replace) to prevent corruption on crash.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path

from app.services.features.product_surface import REMOVED_FEATURE_OVERRIDE_KEYS

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(".myrm/features")
_CONFIG_FILE = _CONFIG_DIR / "user_overrides.json"


def load_user_overrides() -> dict[str, bool]:
    """Load user feature overrides from persistent storage."""
    if not _CONFIG_FILE.exists():
        return {}
    try:
        raw = _CONFIG_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.warning("Invalid feature overrides format, resetting")
            return {}
        overrides = {k: bool(v) for k, v in data.items() if isinstance(k, str)}
        return sanitize_user_overrides(overrides)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load feature overrides: %s", e)
        return {}


def sanitize_user_overrides(overrides: dict[str, bool]) -> dict[str, bool]:
    """Drop overrides for removed/hidden product features and persist when cleaned."""
    from myrm_agent_harness.core.features import registry
    from myrm_agent_harness.core.features.types import FeatureStage

    cleaned = dict(overrides)
    removed_keys: list[str] = []

    for key in list(cleaned.keys()):
        if key in REMOVED_FEATURE_OVERRIDE_KEYS:
            removed_keys.append(key)
            cleaned.pop(key, None)
            continue

        spec = registry.get(key) or registry.get_by_key(key)
        if spec is not None and spec.stage == FeatureStage.REMOVED:
            removed_keys.append(key)
            cleaned.pop(key, None)

    if removed_keys:
        logger.info(
            "Removed stale feature overrides for hidden product surfaces: %s",
            ", ".join(sorted(removed_keys)),
        )
        save_user_overrides(cleaned)

    return cleaned


def save_user_overrides(overrides: dict[str, bool]) -> None:
    """Persist user feature overrides via atomic write (tmp file + os.replace)."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(overrides, indent=2, sort_keys=True)
    fd, tmp_path = tempfile.mkstemp(dir=_CONFIG_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, _CONFIG_FILE)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def set_feature_override(feature_id: str, enabled: bool) -> dict[str, bool]:
    """Set a single feature override and persist. Returns updated overrides."""
    overrides = load_user_overrides()
    overrides[feature_id] = enabled
    save_user_overrides(overrides)
    return overrides


def remove_feature_override(feature_id: str) -> dict[str, bool]:
    """Remove a feature override (reset to default). Returns updated overrides."""
    overrides = load_user_overrides()
    overrides.pop(feature_id, None)
    save_user_overrides(overrides)
    return overrides
