"""Gate sync — toggles feature gates when user progression level changes.

[INPUT]
- app.services.features.feature_config_service (POS: feature override persistence)
- myrm_agent_harness.core.features (POS: runtime feature registry)
- Progression level (int)

[OUTPUT]
- Side effect: enables features gated to the user's new level

[POS]
Bridges progression → feature flags. Called by service.py on level-up.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.features import init_features, registry

from app.services.features.feature_config_service import load_user_overrides, set_feature_override

logger = logging.getLogger(__name__)

# Feature IDs that should be auto-enabled at each level.
# Currently empty because all core features default to enabled/STABLE.
# Populate when new experimental or default-off features need level-gating.
LEVEL_GATED_FEATURES: dict[int, list[str]] = {}


async def sync_gates_for_level(new_level: int) -> None:
    """Enable all features gated at or below the given level.

    Skips features already enabled or not registered in the harness.
    """
    features_to_enable: list[str] = []
    for lvl, feature_ids in LEVEL_GATED_FEATURES.items():
        if lvl <= new_level:
            features_to_enable.extend(feature_ids)

    if not features_to_enable:
        return

    current_overrides = load_user_overrides()
    changed = False

    for feature_id in features_to_enable:
        spec = registry.get(feature_id)
        if spec is None:
            continue
        if current_overrides.get(feature_id) is True:
            continue
        set_feature_override(feature_id, enabled=True)
        changed = True
        logger.info("Progression gate_sync: enabled feature '%s' at level %d", feature_id, new_level)

    if changed:
        updated_overrides = load_user_overrides()
        init_features(overrides=updated_overrides)
