"""Auto-migrate competitor model config into Myrm model settings (Local/Tauri only).

[INPUT]
hermes_config dict (``auxiliary`` section); openclaw_config dict (``agents.defaults``)

[OUTPUT]
migrate_hermes_auxiliary_models(): Hermes per-task auxiliary → Myrm categorical slots
migrate_openclaw_default_model(): OpenClaw default model → Myrm defaultModelConfig

[POS]
Server business layer — wizard-payload-driven model migration, called from
confirm_import_memories. Only active in local/Tauri deployments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config.deploy_mode import is_local_mode
from app.services.config.service import config_service

logger = logging.getLogger(__name__)

_HERMES_TASK_TO_MYRM_SLOT: dict[str, str] = {
    "compression": "liteModel",
    "title_generation": "liteModel",
    "triage_specifier": "liteModel",
    "profile_describer": "liteModel",
    "curator": "liteModel",
    "session_search": "liteModel",
    "flush_memories": "liteModel",
    "web_extract": "liteModel",
    "vision": "visionFallbackModel",
    "approval": "liteModel",
    "mcp": "liteModel",
    "skills_hub": "liteModel",
    "kanban_decomposer": "routingReasoningModel",
}

_PROVIDER_LITELLM_PREFIX: dict[str, str] = {
    "openai": "openai",
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
class AuxiliaryMigrationResult:
    """Result of migrating Hermes auxiliary model configuration."""

    migrated_slots: dict[str, str] = field(default_factory=dict)
    skipped_tasks: list[str] = field(default_factory=list)
    total_tasks_detected: int = 0


def extract_hermes_auxiliary_config(hermes_config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Extract per-task auxiliary model assignments from Hermes config.yaml.

    Hermes format (nested dict):
        auxiliary:
          compression:
            provider: openrouter
            model: meta-llama/llama-3.3-8b-instruct
          vision:
            provider: auto
            model: gpt-4o-mini
    """
    auxiliary = hermes_config.get("auxiliary")
    if not isinstance(auxiliary, dict):
        return {}

    tasks: dict[str, dict[str, str]] = {}
    for task_key, task_config in auxiliary.items():
        if not isinstance(task_config, dict):
            continue
        provider = str(task_config.get("provider", "")).strip()
        model = str(task_config.get("model", "")).strip()
        if model and provider not in ("auto", "main", ""):
            tasks[task_key] = {"provider": provider, "model": model}
        elif model and provider in ("auto", "main"):
            tasks[task_key] = {"provider": "auto", "model": model}

    return tasks


def _resolve_litellm_model(provider: str, model: str) -> str:
    """Convert Hermes provider/model pair to a LiteLLM-compatible model string."""
    if "/" in model:
        return model
    prefix = _PROVIDER_LITELLM_PREFIX.get(provider, provider)
    return f"{prefix}/{model}"


async def migrate_hermes_auxiliary_models(
    hermes_config: dict[str, Any],
) -> AuxiliaryMigrationResult:
    """Detect Hermes auxiliary model config and apply to Myrm's default model slots.

    Only modifies slots that are currently empty (never overwrites user's existing config).
    Only runs in local/Tauri mode.
    """
    if not is_local_mode():
        return AuxiliaryMigrationResult()

    tasks = extract_hermes_auxiliary_config(hermes_config)
    if not tasks:
        return AuxiliaryMigrationResult()

    result = AuxiliaryMigrationResult(total_tasks_detected=len(tasks))

    providers_record = await config_service.get("providers")
    providers_value: dict[str, Any] = (
        providers_record.value if providers_record and isinstance(providers_record.value, dict) else {}
    )
    current_model_config: dict[str, Any] = (
        providers_value.get("defaultModelConfig")
        if isinstance(providers_value.get("defaultModelConfig"), dict)
        else {}
    )

    slot_candidates: dict[str, str] = {}

    for task_key, task_info in tasks.items():
        myrm_slot = _HERMES_TASK_TO_MYRM_SLOT.get(task_key)
        if not myrm_slot:
            result.skipped_tasks.append(task_key)
            continue

        current_slot_value = current_model_config.get(myrm_slot)
        if current_slot_value and isinstance(current_slot_value, dict) and current_slot_value.get("model"):
            result.skipped_tasks.append(task_key)
            continue

        litellm_model = _resolve_litellm_model(task_info["provider"], task_info["model"])
        if myrm_slot not in slot_candidates:
            slot_candidates[myrm_slot] = litellm_model

    if slot_candidates:
        updates = dict(current_model_config)
        for slot, model_name in slot_candidates.items():
            updates[slot] = {"model": model_name}
            result.migrated_slots[slot] = model_name
            logger.info(
                "Hermes auxiliary migration: %s → %s (%s)",
                slot,
                model_name,
                "auto-detected",
            )

        providers_value["defaultModelConfig"] = updates
        await config_service.set(config_key="providers", value=providers_value)

    if result.migrated_slots:
        await _enable_economy_routing_if_unset(None)

    return result


def _litellm_to_primary_selection(litellm_model: str) -> dict[str, str]:
    """Convert a LiteLLM model string to defaultModelConfig primary selection."""
    if "/" not in litellm_model:
        return {"providerId": "openrouter", "model": litellm_model}
    provider_id, model_id = litellm_model.split("/", 1)
    return {"providerId": provider_id, "model": model_id}


def _slot_primary_selection(model_config: dict[str, Any], slot_name: str) -> dict[str, str] | None:
    slot = model_config.get(slot_name)
    if not isinstance(slot, dict):
        return None
    model_name = slot.get("model")
    if not isinstance(model_name, str) or not model_name.strip():
        return None
    return _litellm_to_primary_selection(model_name.strip())


def _routing_slot_has_primary(routing_slot: object) -> bool:
    if not isinstance(routing_slot, dict):
        return False
    primary = routing_slot.get("primary")
    return isinstance(primary, dict) and bool(primary.get("model"))


async def _enable_economy_routing_if_unset(providers_value: dict[str, Any] | None) -> None:
    """Enable Smart Routing defaults for Hermes migrants when not already configured."""
    providers_record = await config_service.get("providers")
    providers_value = (
        providers_value
        if isinstance(providers_value, dict)
        else (providers_record.value if providers_record and isinstance(providers_record.value, dict) else {})
    )
    model_config = providers_value.get("defaultModelConfig")
    if not isinstance(model_config, dict):
        model_config = {}
    routing_config = model_config.get("routingConfig")
    if isinstance(routing_config, dict) and routing_config.get("enabled"):
        return

    empty_slot = {"primary": None, "fallback": None}
    existing_routing = routing_config if isinstance(routing_config, dict) else {}
    light_slot = existing_routing.get("lightModel") if isinstance(existing_routing.get("lightModel"), dict) else empty_slot
    reasoning_slot = (
        existing_routing.get("reasoningModel")
        if isinstance(existing_routing.get("reasoningModel"), dict)
        else empty_slot
    )

    light_primary = _slot_primary_selection(model_config, "liteModel")
    if light_primary and not _routing_slot_has_primary(light_slot):
        light_slot = {**light_slot, "primary": light_primary}

    reasoning_primary = _slot_primary_selection(model_config, "routingReasoningModel")
    if reasoning_primary and not _routing_slot_has_primary(reasoning_slot):
        reasoning_slot = {**reasoning_slot, "primary": reasoning_primary}

    model_config["routingConfig"] = {
        "enabled": True,
        "lightModel": light_slot or empty_slot,
        "reasoningModel": reasoning_slot or empty_slot,
    }
    providers_value["defaultModelConfig"] = model_config
    await config_service.set(config_key="providers", value=providers_value)
    logger.info("Hermes economy pack: enabled Smart Routing defaults")


async def migrate_openclaw_default_model(openclaw_config: dict[str, Any]) -> str | None:
    """Extract OpenClaw default model and write to Myrm's defaultModelConfig.

    OpenClaw stores the primary model in ``agents.defaults.model`` as either a
    bare string (``"anthropic/claude-opus-4-6"``) or ``{"primary": "<value>"}``.
    An optional alias catalog at ``agents.defaults.models`` maps display names
    to real API IDs.

    Only writes when ``defaultModelConfig.baseModel`` is currently empty.
    Returns the resolved model string on success, None otherwise.
    """
    if not is_local_mode():
        return None

    model_value = (openclaw_config.get("agents") or {}).get("defaults", {}).get("model")
    if model_value is None:
        return None

    model_str = model_value.get("primary") if isinstance(model_value, dict) else model_value
    if not isinstance(model_str, str) or not model_str.strip():
        return None
    model_str = model_str.strip()

    model_catalog = (openclaw_config.get("agents") or {}).get("defaults", {}).get("models", {})
    if isinstance(model_catalog, dict) and model_str not in model_catalog:
        for api_id, entry in model_catalog.items():
            if not isinstance(api_id, str):
                continue
            if isinstance(entry, dict) and entry.get("alias") == model_str:
                model_str = api_id
                break
            if isinstance(entry, str) and entry == model_str:
                model_str = api_id
                break

    providers_record = await config_service.get("providers")
    providers_value: dict[str, Any] = (
        providers_record.value if providers_record and isinstance(providers_record.value, dict) else {}
    )
    existing_cfg = providers_value.get("defaultModelConfig")
    if isinstance(existing_cfg, dict):
        base_model = existing_cfg.get("baseModel")
        if isinstance(base_model, dict) and (base_model.get("primary") or base_model.get("selection")):
            logger.debug("OpenClaw default model migration skipped: baseModel already configured")
            return None

    if "/" not in model_str:
        model_str = f"openrouter/{model_str}"

    provider_id, model_id = model_str.split("/", 1)

    default_model_cfg = providers_value.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        default_model_cfg = {}
    default_model_cfg["baseModel"] = {
        "primary": {"providerId": provider_id, "model": model_id},
    }
    providers_value["defaultModelConfig"] = default_model_cfg
    await config_service.set(config_key="providers", value=providers_value)
    logger.info("OpenClaw default model migrated: %s", model_str)
    return model_str
