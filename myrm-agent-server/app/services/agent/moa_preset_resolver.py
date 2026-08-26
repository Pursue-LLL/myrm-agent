"""Session-level MoA preset activation for agent-loop advisor overlay.

[INPUT]
- Agent profile ``engine_params`` (includes ``moa_overlay`` definition)
- Request ``active_moa_preset_id`` (chat/session picker selection)

[OUTPUT]
- ``apply_moa_preset_activation``: returns engine_params with overlay enabled only for active preset
- ``resolve_preset_reference_selections``: refs for a preset id (strict per-preset when ``presets`` exists)
- ``resolve_effective_moa_preset_id``: resolves active preset accounting for REASONING tier auto-gate

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

_PRESET_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "reference_reasoning_effort",
        "reference_max_tokens",
        "reference_temperature",
        "min_successful",
    }
)


def _moa_overlay_block(
    engine_params: dict[str, object] | None,
) -> dict[str, object] | None:
    if not engine_params:
        return None
    raw = engine_params.get("moa_overlay")
    if not isinstance(raw, dict):
        return None
    return raw


def moa_overlay_from_engine_params(
    engine_params: dict[str, object] | None,
) -> dict[str, object] | None:
    """Return the ``moa_overlay`` block from agent engine_params when present."""
    return _moa_overlay_block(engine_params)


def _top_level_reference_selections(overlay: dict[str, object]) -> list[object]:
    refs = overlay.get("reference_model_selections")
    return refs if isinstance(refs, list) else []


def _preset_blocks(overlay: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = overlay.get("presets")
    if not isinstance(raw, dict):
        return {}
    blocks: dict[str, dict[str, object]] = {}
    for preset_id, block in raw.items():
        if preset_id in VALID_MOA_PRESET_IDS and isinstance(block, dict):
            blocks[preset_id] = block
    return blocks


def _has_presets_key(overlay: dict[str, object]) -> bool:
    return "presets" in overlay


def resolve_preset_reference_selections(
    overlay: dict[str, object],
    preset_id: str,
) -> list[object]:
    """Return reference_model_selections for a preset.

    When ``presets`` exists, each preset block is authoritative (empty list = no refs).
    Top-level ``reference_model_selections`` is fallback only for legacy profiles without ``presets``.
    """
    if _has_presets_key(overlay):
        block = _preset_blocks(overlay).get(preset_id)
        if block is None:
            return []
        refs = block.get("reference_model_selections")
        return refs if isinstance(refs, list) else []
    return _top_level_reference_selections(overlay)


def iter_all_reference_selections(
    overlay: dict[str, object],
) -> list[dict[str, object]]:
    """Collect unique reference selections across presets and top-level (org-policy)."""
    seen: set[tuple[str, str]] = set()
    collected: list[dict[str, object]] = []

    def _add(item: object) -> None:
        if not isinstance(item, dict):
            return
        provider_id = item.get("providerId")
        model = item.get("model")
        if not isinstance(provider_id, str) or not isinstance(model, str):
            return
        key = (provider_id, model)
        if key in seen:
            return
        seen.add(key)
        collected.append(item)

    for preset_id in VALID_MOA_PRESET_IDS:
        for item in resolve_preset_reference_selections(overlay, preset_id):
            _add(item)
    for item in _top_level_reference_selections(overlay):
        _add(item)
    return collected


def is_moa_preset_configured(engine_params: dict[str, object] | None) -> bool:
    """True when agent profile has a MoA preset ready for the model picker."""
    overlay = _moa_overlay_block(engine_params)
    if overlay is None:
        return False
    if not overlay.get("enabled"):
        return False
    has_preset_refs = any(len(resolve_preset_reference_selections(overlay, preset_id)) > 0 for preset_id in VALID_MOA_PRESET_IDS)
    if _has_presets_key(overlay):
        return has_preset_refs
    return has_preset_refs or len(_top_level_reference_selections(overlay)) > 0


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
    activate = (
        overlay.get("enabled") is True and active_moa_preset_id is not None and active_moa_preset_id in VALID_MOA_PRESET_IDS
    )
    overlay_copy["enabled"] = activate
    if activate and active_moa_preset_id is not None:
        preset_block = _preset_blocks(overlay_copy).get(active_moa_preset_id)
        refs = resolve_preset_reference_selections(overlay_copy, active_moa_preset_id)
        overlay_copy["reference_model_selections"] = list(refs)

        if preset_block is not None:
            for key in _PRESET_OVERRIDE_KEYS:
                if key in preset_block:
                    overlay_copy[key] = preset_block[key]

        preset_overrides = _PRESET_PARAM_OVERRIDES.get(active_moa_preset_id, {})
        for key, value in preset_overrides.items():
            if preset_block is None or key not in preset_block:
                overlay_copy[key] = value

    params["moa_overlay"] = overlay_copy
    return params


def resolve_effective_moa_preset_id(
    engine_params: dict[str, object] | None,
    requested_preset_id: str | None = None,
    routing_tier: str | None = None,
    auto_moa_reasoning: bool = False,
    auto_moa_preset_id: str | None = None,
) -> str | None:
    """Resolve effective MoA preset id to activate for the current turn.

    1. If user explicitly requested a valid preset in the model picker, honor it.
    2. If auto_moa_reasoning is True (or agent profile moa_overlay.auto_on_reasoning is True)
       and the task was routed to REASONING tier, automatically select an appropriate MoA preset
       (preferring auto_moa_preset_id, 'review', or 'default' with configured reference models).
    3. Otherwise, return None (single-model execution).
    """
    if requested_preset_id is not None and requested_preset_id in VALID_MOA_PRESET_IDS:
        return requested_preset_id

    overlay = _moa_overlay_block(engine_params)
    if overlay is None:
        return None

    # Check per-agent override or request-level flag
    agent_auto = overlay.get("auto_on_reasoning")
    is_auto_enabled = bool(agent_auto if isinstance(agent_auto, bool) else auto_moa_reasoning)

    # Check if routing tier is REASONING
    is_reasoning_tier = routing_tier in ("reasoning", "REASONING")

    if is_auto_enabled and is_reasoning_tier and is_moa_preset_configured(engine_params):
        candidate_preset = (
            auto_moa_preset_id
            if (auto_moa_preset_id is not None and auto_moa_preset_id in VALID_MOA_PRESET_IDS)
            else MOA_PRESET_REVIEW_ID
        )
        if len(resolve_preset_reference_selections(overlay, candidate_preset)) > 0:
            return candidate_preset
        # Fallback to default if candidate has no refs
        if len(resolve_preset_reference_selections(overlay, MOA_PRESET_DEFAULT_ID)) > 0:
            return MOA_PRESET_DEFAULT_ID
        # Fallback to fast if default has no refs
        if len(resolve_preset_reference_selections(overlay, MOA_PRESET_FAST_ID)) > 0:
            return MOA_PRESET_FAST_ID
        return candidate_preset

    return None
