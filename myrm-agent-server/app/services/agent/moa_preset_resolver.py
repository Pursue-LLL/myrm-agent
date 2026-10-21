"""Session-level MoA preset activation for agent-loop advisor overlay.

[INPUT]
- Agent profile ``engine_params`` (includes ``moa_overlay`` definition and activation_mode)
- Request ``active_moa_preset_id`` (chat/session picker selection)
- Task context ``routing_tier``, ``task_tools``, ``has_risk_trigger``

[OUTPUT]
- ``apply_moa_preset_activation``: returns engine_params with overlay enabled for active preset or auto-activated policy
- ``resolve_preset_reference_selections``: refs for a preset id (strict per-preset when ``presets`` exists)
- ``resolve_effective_moa_preset_id``: resolves active preset accounting for picker request, REASONING tier, and auto-activation policy
- ``resolve_profile_moa_activation_mode``: extracts declarative activation mode from agent profile
- ``MoAActivationMode``: literal type ("manual", "always", "risk_triggered")

[POS]
Business-layer resolver. Implements Agent Profile Advisor Auto-Activation Policy,
evaluating declarative profile policies (manual, always, risk_triggered) while
maintaining explicit user picker choice as top priority.
"""

from __future__ import annotations

from typing import Literal

MoAActivationMode = Literal["manual", "always", "risk_triggered"]

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

DEFAULT_RISK_TRIGGER_TOOLS: frozenset[str] = frozenset(
    {
        "file_write_tool",
        "file_edit_tool",
        "bash_code_execute_tool",
        "skill_manage_tool",
        "skill_market_tool",
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


def resolve_profile_moa_activation_mode(
    engine_params: dict[str, object] | None,
) -> MoAActivationMode:
    """Extract declarative activation mode from agent profile moa_overlay."""
    overlay = _moa_overlay_block(engine_params)
    if overlay is None or not overlay.get("enabled"):
        return "manual"
    raw_mode = overlay.get("activation_mode")
    if raw_mode in ("manual", "always", "risk_triggered"):
        return raw_mode  # type: ignore[return-value]
    if overlay.get("auto_on_reasoning") is True:
        return "risk_triggered"
    return "manual"


def resolve_effective_moa_preset_id(
    engine_params: dict[str, object] | None,
    requested_preset_id: str | None = None,
    routing_tier: str | None = None,
    auto_moa_reasoning: bool = False,
    auto_moa_preset_id: str | None = None,
    task_tools: list[str] | tuple[str, ...] | None = None,
    has_risk_trigger: bool = False,
) -> str | None:
    """Resolve effective MoA preset id to activate for the current turn.

    Priority:
    1. Explicit User Picker Request:
       - If valid preset id requested, honor it.
       - If explicitly requested 'none'/'disabled', turn off overlay.
    2. Profile Auto-Activation Policy:
       - 'always': auto-activate default preset (fallback to any configured preset).
       - 'risk_triggered': auto-activate when risk condition is met (reasoning tier,
         risk trigger flag, or task matches risk tools).
       - 'manual': keep single model (None).
    """
    if requested_preset_id is not None:
        if requested_preset_id in VALID_MOA_PRESET_IDS:
            return requested_preset_id
        if requested_preset_id in ("none", "off", "disabled"):
            return None

    overlay = _moa_overlay_block(engine_params)
    if overlay is None or not is_moa_preset_configured(engine_params):
        return None

    activation_mode = resolve_profile_moa_activation_mode(engine_params)
    if auto_moa_reasoning and activation_mode == "manual":
        activation_mode = "risk_triggered"

    if activation_mode == "manual":
        return None

    def _select_candidate(preferred_id: str | None) -> str | None:
        candidates = [preferred_id] if preferred_id in VALID_MOA_PRESET_IDS else []
        candidates.extend([MOA_PRESET_REVIEW_ID, MOA_PRESET_DEFAULT_ID, MOA_PRESET_FAST_ID])
        for cid in candidates:
            if cid and len(resolve_preset_reference_selections(overlay, cid)) > 0:
                return cid
        return candidates[0] if candidates else None

    raw_default = overlay.get("default_preset_id")
    target_preset = str(raw_default) if isinstance(raw_default, str) else (auto_moa_preset_id or MOA_PRESET_REVIEW_ID)

    if activation_mode == "always":
        return _select_candidate(target_preset)

    if activation_mode == "risk_triggered":
        is_reasoning_tier = routing_tier in ("reasoning", "REASONING")
        custom_risk_tools = overlay.get("risk_trigger_tools")
        risk_tools = set(custom_risk_tools) if isinstance(custom_risk_tools, (list, tuple, set)) else DEFAULT_RISK_TRIGGER_TOOLS
        task_tool_set = set(task_tools or ())
        has_tool_risk = bool(task_tool_set & risk_tools)

        if is_reasoning_tier or has_risk_trigger or has_tool_risk:
            return _select_candidate(target_preset)

    return None


def apply_moa_preset_activation(
    engine_params: dict[str, object] | None,
    active_moa_preset_id: str | None = None,
    routing_tier: str | None = None,
    task_tools: list[str] | tuple[str, ...] | None = None,
    has_risk_trigger: bool = False,
) -> dict[str, object] | None:
    """Enable ``moa_overlay`` for active preset via explicit request or auto-activation policy."""
    if engine_params is None:
        return None

    params = dict(engine_params)
    overlay = _moa_overlay_block(params)
    if overlay is None:
        return params

    effective_preset_id = resolve_effective_moa_preset_id(
        params,
        requested_preset_id=active_moa_preset_id,
        routing_tier=routing_tier,
        task_tools=task_tools,
        has_risk_trigger=has_risk_trigger,
    )

    overlay_copy = dict(overlay)
    activate = overlay.get("enabled") is True and effective_preset_id is not None and effective_preset_id in VALID_MOA_PRESET_IDS
    overlay_copy["enabled"] = activate
    if activate and effective_preset_id is not None:
        preset_block = _preset_blocks(overlay_copy).get(effective_preset_id)
        refs = resolve_preset_reference_selections(overlay_copy, effective_preset_id)
        overlay_copy["reference_model_selections"] = list(refs)
        overlay_copy["active_preset_id"] = effective_preset_id

        if preset_block is not None:
            for key in _PRESET_OVERRIDE_KEYS:
                if key in preset_block:
                    overlay_copy[key] = preset_block[key]

        preset_overrides = _PRESET_PARAM_OVERRIDES.get(effective_preset_id, {})
        for key, value in preset_overrides.items():
            if preset_block is None or key not in preset_block:
                overlay_copy[key] = value

    params["moa_overlay"] = overlay_copy
    return params
