"""[INPUT]
- .common (POS: shared constants and preset state)

[OUTPUT]
- apply_second_brain_preset

[POS]
Second Brain preset: the write path (idempotent apply with rollback).
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from app.services.config.service import config_service
from app.services.onboarding.schemas import (
    SecondBrainApplyResponse,
    SecondBrainPresetState,
)
from app.services.wiki.vault import seed_agent_vault_from_default

from . import checks, common, cron_setup, mutations
from .common import (
    _CONFIG_KEY,
    _DEVICE_ID,
    logger,
)


async def apply_second_brain_preset(*, accept_language: str | None = None) -> SecondBrainApplyResponse:
    locale = common._normalize_locale(accept_language)
    previous_state = await common._load_preset_state()
    previous_snapshot = deepcopy(previous_state.model_dump(mode="json")) if previous_state else None
    mutation = common._ApplyMutation()

    try:
        agent_id, agent_name, agent_created = await checks._resolve_agent(
            locale=locale,
            existing_state=previous_state,
        )
        if agent_created:
            mutation.created_agent_id = agent_id

        seed_result = seed_agent_vault_from_default(agent_id)
        if seed_result.files_copied:
            logger.info(
                "Second Brain preset seeded %d wiki files into agent %s",
                seed_result.files_copied,
                agent_id,
            )

        cron_job_id, cron_created = await cron_setup._ensure_read_it_later_cron(agent_id=agent_id, locale=locale)
        if cron_created and cron_job_id:
            mutation.created_cron_job_ids = (
                *mutation.created_cron_job_ids,
                cron_job_id,
            )

        delta_cron_job_id, delta_cron_created = await cron_setup._ensure_wiki_morning_delta_cron(
            agent_id=agent_id,
            locale=locale,
        )
        if delta_cron_created and delta_cron_job_id:
            mutation.created_cron_job_ids = (
                *mutation.created_cron_job_ids,
                delta_cron_job_id,
            )

        maintain_cron_job_id, maintain_cron_created = await cron_setup._ensure_wiki_maintain_cron(
            agent_id=agent_id,
            locale=locale,
        )
        if maintain_cron_created and maintain_cron_job_id:
            mutation.created_cron_job_ids = (
                *mutation.created_cron_job_ids,
                maintain_cron_job_id,
            )

        await mutations._maybe_enable_wiki_gmail_source()

        applied_at = datetime.now(UTC).isoformat()
        await common._save_preset_state(
            SecondBrainPresetState(
                agent_id=agent_id,
                agent_name=agent_name,
                cron_job_id=cron_job_id,
                delta_cron_job_id=delta_cron_job_id,
                maintain_cron_job_id=maintain_cron_job_id,
                applied_at=applied_at,
            )
        )

        checklist = await checks._build_checklist(
            agent_id=agent_id,
            cron_job_id=cron_job_id,
            delta_cron_job_id=delta_cron_job_id,
            maintain_cron_job_id=maintain_cron_job_id,
        )
        message = mutations._apply_success_message(
            locale=locale,
            vault_files_seeded=seed_result.files_copied,
        )
        return SecondBrainApplyResponse(
            success=True,
            message=message,
            agent_id=agent_id,
            agent_name=agent_name,
            cron_job_id=cron_job_id,
            delta_cron_job_id=delta_cron_job_id,
            maintain_cron_job_id=maintain_cron_job_id,
            checklist=checklist,
            applied_at=applied_at,
        )
    except Exception:
        await mutations._rollback_apply(mutation)
        if previous_snapshot is not None:
            try:
                await config_service.set(
                    config_key=_CONFIG_KEY,
                    value=previous_snapshot,
                    device_id=f"{_DEVICE_ID}-rollback",
                )
            except Exception as exc:
                logger.warning("Failed to restore secondBrainPreset snapshot: %s", exc)
        raise
