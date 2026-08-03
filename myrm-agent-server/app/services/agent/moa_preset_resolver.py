"""Session-level MoA preset activation for agent-loop advisor overlay.

[INPUT]
- Agent profile ``engine_params`` (includes ``moa_overlay`` definition)
- Request ``active_moa_preset_id`` (chat/session picker selection)

[OUTPUT]
- ``apply_moa_preset_activation``: returns engine_params with overlay enabled only for active preset

[POS]
Business-layer resolver. Profile ``moa_overlay.enabled`` means preset is configured and
available in the model picker — not "always run overlay on every message".
"""

from __future__ import annotations

MOA_PRESET_DEFAULT_ID = "default"
MOA_PRESET_REVIEW_ID = "review"
MOA_PRESET_FAST_ID = "fast"

VALID_MOA_PRESET_IDS: frozenset[str] = frozenset(
    {
        MOA_PRESET_DEFAULT_ID,
        MOA_PRESET_REVIEW_ID,
        MOA_PRESET_FAST_ID,
    }
)

_PRESET_PARAM_OVERRIDES: dict[str, dict[str, object]] = {
    MOA_PRESET_DEFAULT_ID: {},
    MOA_PRESET_REVIEW_ID: {
        "reference_reasoning_effort": "high",
    },
    MOA_PRESET_FAST_ID: {
        "reference_max_tokens": 600,
        "reference_reasoning_effort": "low",
    },
}


def _moa_overlay_block(engine_params: dict[str, object] | None) -> dict[str, object] | None:
    if not engine_params:
        return None
    raw = engine_params.get("moa_overlay")
    if not isinstance(raw, dict):
        return None
    return raw


def is_moa_preset_configured(engine_params: dict[str, object] | None) -> bool:
    """True when agent profile has a MoA preset ready for the model picker."""
    overlay = _moa_overlay_block(engine_params)
    if overlay is None:
        return False
    if not overlay.get("enabled"):
        return False
    refs = overlay.get("reference_model_selections")
    return isinstance(refs, list) and len(refs) > 0


def apply_moa_preset_activation(
    engine_params: dict[str, object] | None,
    active_moa_preset_id: str | None,
) -> dict[str, object] | None:
    """Enable ``moa_overlay`` only when the chat picker activated a valid preset."""
    if engine_params is None:
        return None

    params = dict(engine_params)
    overlay = _moa_overlay_block(params)
    if overlay is None:
        return params

    overlay_copy = dict(overlay)
    configured = is_moa_preset_configured(params)

    activate = (
        configured
        and active_moa_preset_id is not None
        and active_moa_preset_id in VALID_MOA_PRESET_IDS
    )
    overlay_copy["enabled"] = activate
    if activate and active_moa_preset_id is not None:
        preset_overrides = _PRESET_PARAM_OVERRIDES.get(active_moa_preset_id, {})
        for key, value in preset_overrides.items():
            overlay_copy[key] = value
    params["moa_overlay"] = overlay_copy
    return params
