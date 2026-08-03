"""Hermes ``moa.presets`` → Myrm agent ``engine_params.moa_overlay`` migration.

[INPUT]
- Hermes config.yaml ``moa`` block (flat legacy or named presets)
- app.services.agent.agent_service::AgentService (POS: Agent CRUD)
- app.services.agent.profile_snapshot_service::ProfileSnapshotService (POS: Agent 配置快照与回滚)
- Target agent id from migration wizard instruction lane

[OUTPUT]
- ``build_moa_overlay_from_hermes_config``: Myrm overlay dict for engine_params
- ``migrate_hermes_moa_overlay``: apply to agent profile (non-destructive)
- ``_filter_valid_reference_selections``: drop refs that fail WebUI provider resolution

[POS]
Server migration lane — maps Hermes reference models into Myrm picker-ready overlay.
Hermes aggregator is intentionally not migrated (Myrm primary model absorbs advisors).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.database.dto import AgentUpdate
from app.database.repositories.uow import UnitOfWork
from app.services.agent.agent_service import AgentService
from app.services.agent.profile_snapshot_service import ProfileSnapshotService

logger = logging.getLogger(__name__)

DEFAULT_PRESET_NAME = "default"

_HERMES_PROVIDER_TO_MYRM_ID: dict[str, str] = {
    "openai": "openai",
    "openai-codex": "openai",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "google": "google",
    "groq": "groq",
    "xai": "xai",
    "mistral": "mistral",
    "deepseek": "deepseek",
    "nous": "openrouter",
}


@dataclass
class MoaOverlayMigrationResult:
    """Outcome of Hermes MoA overlay migration onto an agent profile."""

    configured: bool = False
    preset_name: str | None = None
    reference_count: int = 0
    skipped_reason: str | None = None
    skipped_refs: list[str] = field(default_factory=list)
    applied_fields: list[str] = field(default_factory=list)


def extract_hermes_moa_block(hermes_config: dict[str, Any]) -> dict[str, Any] | None:
    """Return the raw Hermes ``moa`` section when present."""
    moa = hermes_config.get("moa")
    return moa if isinstance(moa, dict) else None


def hermes_config_has_moa(hermes_config: dict[str, Any]) -> bool:
    """True when Hermes config contains a usable MoA preset definition."""
    moa = extract_hermes_moa_block(hermes_config)
    if moa is None:
        return False
    return build_moa_overlay_from_hermes_config(moa) is not None


def resolve_hermes_moa_preset(
    moa_raw: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Pick default (or first) Hermes MoA preset from config."""
    presets: dict[str, dict[str, Any]] = {}
    presets_raw = moa_raw.get("presets")
    if isinstance(presets_raw, dict):
        for name, preset in presets_raw.items():
            clean_name = str(name or "").strip()
            if clean_name and isinstance(preset, dict):
                presets[clean_name] = preset

    if not presets and moa_raw.get("reference_models") is not None:
        presets[DEFAULT_PRESET_NAME] = moa_raw

    if not presets:
        return None

    default_name = str(moa_raw.get("default_preset") or "").strip()
    if default_name not in presets:
        default_name = next(iter(presets))

    preset = presets[default_name]
    if not preset.get("enabled", True):
        for name, candidate in presets.items():
            if candidate.get("enabled", True):
                return name, candidate
        return None

    return default_name, preset


def _coerce_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"0", "false", "no", "off"}:
            return False
        if text in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


def _clean_reference_slot(slot: object) -> dict[str, Any] | None:
    if not isinstance(slot, dict):
        return None
    provider = str(slot.get("provider") or "").strip()
    model = str(slot.get("model") or "").strip()
    if not provider or not model:
        return None
    if provider.lower() == "moa":
        return None
    if not _coerce_bool(slot.get("enabled"), True):
        return None
    if provider.lower() in {"auto", "main"}:
        return None
    clean: dict[str, Any] = {"provider": provider, "model": model}
    effort = slot.get("reasoning_effort")
    if isinstance(effort, str) and effort.strip():
        clean["reasoning_effort"] = effort.strip().lower()
    max_tokens = slot.get("max_tokens")
    if isinstance(max_tokens, int) and max_tokens > 0:
        clean["max_tokens"] = max_tokens
    return clean


def hermes_slot_to_myrm_selection(slot: dict[str, Any]) -> dict[str, str] | None:
    """Map a Hermes provider/model slot to Myrm ``reference_model_selections`` entry."""
    provider = str(slot.get("provider", "")).strip()
    model = str(slot.get("model", "")).strip()
    if not provider or not model:
        return None
    provider_id = _HERMES_PROVIDER_TO_MYRM_ID.get(provider.lower(), provider.lower())
    return {"providerId": provider_id, "model": model}


def _parse_reference_models(preset: dict[str, Any]) -> list[dict[str, str]]:
    raw_refs = preset.get("reference_models")
    if isinstance(raw_refs, str):
        try:
            raw_refs = json.loads(raw_refs)
        except (json.JSONDecodeError, ValueError):
            raw_refs = []
    if not isinstance(raw_refs, list):
        raw_refs = [raw_refs] if isinstance(raw_refs, dict) else []

    selections: list[dict[str, str]] = []
    for item in raw_refs:
        cleaned = _clean_reference_slot(item)
        if cleaned is None:
            continue
        selection = hermes_slot_to_myrm_selection(cleaned)
        if selection is not None:
            selections.append(selection)
    return selections


def _parse_fanout(raw: object) -> tuple[str, int]:
    if isinstance(raw, dict):
        mode = str(raw.get("mode") or "").strip().lower()
        if mode == "every_n":
            n_raw = raw.get("n", 2)
            n = int(n_raw) if isinstance(n_raw, int) else 2
            return "every_n", max(2, n)
        if mode in {"user_turn", "per_iteration"}:
            return mode, 2

    text = str(raw or "user_turn").strip().lower()
    if text.startswith("every_n:"):
        try:
            n = int(text.split(":", 1)[1].strip())
            return "every_n", max(2, n)
        except (ValueError, IndexError):
            pass
    if text in {"user_turn", "per_iteration"}:
        return text, 2
    return "user_turn", 2


def _map_privacy_filter(raw: object) -> str:
    if raw is True:
        return "full"
    mode = str(raw or "").strip().lower()
    if mode == "display":
        return "display"
    if mode in {"full", "true", "on", "yes", "1"}:
        return "full"
    return "off"


def _coerce_int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value > 0:
        return int(value)
    return None


def _coerce_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _resolve_reasoning_effort(
    preset: dict[str, Any], refs_raw: list[object]
) -> str | None:
    for item in refs_raw:
        if isinstance(item, dict):
            effort = item.get("reasoning_effort")
            if isinstance(effort, str) and effort.strip():
                return effort.strip().lower()
    preset_effort = preset.get("reference_reasoning_effort")
    if isinstance(preset_effort, str) and preset_effort.strip():
        return preset_effort.strip().lower()
    return None


def build_moa_overlay_from_hermes_config(
    moa_raw: dict[str, Any],
) -> dict[str, object] | None:
    """Build Myrm ``engine_params.moa_overlay`` from Hermes ``moa`` config."""
    resolved = resolve_hermes_moa_preset(moa_raw)
    if resolved is None:
        return None
    _preset_name, preset = resolved

    refs_raw = preset.get("reference_models")
    if isinstance(refs_raw, str):
        try:
            refs_raw = json.loads(refs_raw)
        except (json.JSONDecodeError, ValueError):
            refs_raw = []
    if not isinstance(refs_raw, list):
        refs_raw = [refs_raw] if isinstance(refs_raw, dict) else []

    selections = _parse_reference_models(preset)
    if not selections:
        return None

    fanout, every_n = _parse_fanout(preset.get("fanout", moa_raw.get("fanout")))
    overlay: dict[str, object] = {
        "enabled": True,
        "reference_model_selections": selections,
        "fanout": fanout,
        "min_successful": 1,
        "reference_temperature": _coerce_float(
            preset.get("reference_temperature"), 0.6
        ),
        "timeout_per_model": _coerce_float(
            preset.get("reference_timeout", moa_raw.get("reference_timeout")),
            120.0,
        ),
        "timeout_total": 300.0,
        "privacy_filter": _map_privacy_filter(moa_raw.get("privacy_filter")),
    }

    ref_max = _coerce_int_or_none(preset.get("reference_max_tokens"))
    if ref_max is not None:
        overlay["reference_max_tokens"] = ref_max

    reasoning = _resolve_reasoning_effort(preset, refs_raw)
    if reasoning and reasoning != "none":
        overlay["reference_reasoning_effort"] = reasoning

    if fanout == "every_n":
        overlay["every_n"] = every_n

    return overlay


async def _filter_valid_reference_selections(
    selections: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[str]]:
    """Keep reference selections resolvable against current WebUI provider config."""
    if not selections:
        return [], []

    try:
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.services.agent.params import ModelSelection, _resolve_model_config

        configs = await load_user_configs()
        providers_dict = configs.providers_dict if configs else None
        if not providers_dict:
            return selections, []

        valid: list[dict[str, str]] = []
        skipped: list[str] = []
        for sel in selections:
            provider_id = sel.get("providerId", "")
            model = sel.get("model", "")
            label = f"{provider_id}/{model}"
            try:
                ms = ModelSelection(provider_id=provider_id, model=model)
                await _resolve_model_config(ms, providers_dict)
            except Exception:
                skipped.append(label)
                logger.info("Hermes MoA migration: skipping unresolvable ref %s", label)
                continue
            valid.append(sel)
        return valid, skipped
    except Exception as exc:
        logger.warning("Hermes MoA migration: provider validation unavailable: %s", exc)
        return selections, []


def agent_has_moa_overlay_refs(engine_params: dict[str, object] | None) -> bool:
    """True when agent profile already defines MoA reference models."""
    if not engine_params:
        return False
    overlay = engine_params.get("moa_overlay")
    if not isinstance(overlay, dict):
        return False
    refs = overlay.get("reference_model_selections")
    return isinstance(refs, list) and len(refs) > 0


async def migrate_hermes_moa_overlay(
    hermes_config: dict[str, Any],
    target_agent_id: str,
) -> MoaOverlayMigrationResult:
    """Apply Hermes MoA reference models to target agent ``engine_params.moa_overlay``.

    Skips when the agent already has reference models configured.
    """
    result = MoaOverlayMigrationResult()
    if not target_agent_id:
        result.skipped_reason = "no_target_agent"
        return result

    moa_raw = extract_hermes_moa_block(hermes_config)
    if moa_raw is None:
        result.skipped_reason = "no_moa_block"
        return result

    resolved = resolve_hermes_moa_preset(moa_raw)
    if resolved is None:
        result.skipped_reason = "no_usable_preset"
        return result
    preset_name, _preset = resolved

    overlay = build_moa_overlay_from_hermes_config(moa_raw)
    if overlay is None:
        result.skipped_reason = "no_reference_models"
        return result

    raw_selections = overlay.get("reference_model_selections")
    if isinstance(raw_selections, list):
        filtered, skipped = await _filter_valid_reference_selections(raw_selections)
        result.skipped_refs = skipped
        if not filtered:
            result.skipped_reason = "no_resolvable_providers"
            return result
        overlay["reference_model_selections"] = filtered

    agent = await AgentService.get_agent_by_id(target_agent_id)
    if agent is None:
        result.skipped_reason = "agent_not_found"
        return result

    existing_params: dict[str, object] = (
        dict(agent.engine_params) if isinstance(agent.engine_params, dict) else {}
    )
    if agent_has_moa_overlay_refs(existing_params):
        result.skipped_reason = "already_configured"
        result.configured = True
        return result

    async with UnitOfWork() as uow:
        await ProfileSnapshotService.save_profile_snapshot(
            target_agent_id,
            reason="hermes-moa-migration",
            uow=uow,
        )

    merged_params = {**existing_params, "moa_overlay": overlay}
    updated = await AgentService.update_agent(
        target_agent_id,
        AgentUpdate(engine_params=merged_params),
    )
    if updated is None:
        result.skipped_reason = "update_failed"
        return result

    ref_count = len(overlay.get("reference_model_selections", []))
    logger.info(
        "Hermes MoA migration: preset=%s refs=%d → agent %s",
        preset_name,
        ref_count,
        target_agent_id,
    )
    result.configured = True
    result.preset_name = preset_name
    result.reference_count = ref_count if isinstance(ref_count, int) else 0
    result.applied_fields = sorted(overlay.keys())
    return result
