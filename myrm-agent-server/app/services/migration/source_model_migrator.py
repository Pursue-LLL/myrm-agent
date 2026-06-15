"""Auto-migrate Hermes auxiliary model config into Myrm model slots (Local/Tauri only).

[INPUT]
source_payload_loader hermes_config dict; Hermes config.yaml ``auxiliary`` section

[OUTPUT]
migrate_hermes_auxiliary_models(): detect and convert Hermes per-task auxiliary models
to Myrm's categorical model slots (lite/vision/reasoning)

[POS]
Server business layer — zero-friction model migration from Hermes installs.
Only active in local/Tauri deployments (SaaS sandboxes cannot access user filesystems).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
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

    current_config = await config_service.get("defaultModelConfig")
    current_model_config: dict[str, Any] = (
        current_config.value if current_config and isinstance(current_config.value, dict) else {}
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

        await config_service.set(config_key="defaultModelConfig", value=updates)

    return result


async def detect_and_migrate_hermes_models() -> AuxiliaryMigrationResult | None:
    """Top-level entry: scan for Hermes config.yaml and migrate auxiliary models.

    Called during app startup in local/Tauri mode.
    Returns None if not in local mode or no Hermes installation found.
    """
    if not is_local_mode():
        return None

    hermes_root = Path.home() / ".hermes"
    config_path = hermes_root / "config.yaml"

    if not config_path.is_file():
        return None

    try:
        import yaml

        with open(config_path) as f:
            hermes_config = yaml.safe_load(f)

        if not isinstance(hermes_config, dict):
            return None

        result = await migrate_hermes_auxiliary_models(hermes_config)
        if result.migrated_slots:
            logger.info(
                "Hermes auxiliary model migration complete: %d slots migrated from %d detected tasks",
                len(result.migrated_slots),
                result.total_tasks_detected,
            )
        return result
    except Exception as e:
        logger.warning("Hermes auxiliary model migration failed: %s", e)
        return None
