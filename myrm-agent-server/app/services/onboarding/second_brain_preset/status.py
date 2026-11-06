"""[INPUT]
- .common (POS: shared constants and preset state)

[OUTPUT]
- get_second_brain_preset_status

[POS]
Second Brain preset: the read path (status + checklist).
"""

from __future__ import annotations

from app.services.agent.agent_service import AgentService
from app.services.onboarding.schemas import (
    SecondBrainStatusResponse,
)

from . import checks, common, cron_setup
from .common import (
    logger,
)


async def get_second_brain_preset_status(*, accept_language: str | None = None) -> SecondBrainStatusResponse:
    await cron_setup._run_read_it_later_hygiene()
    state = await common._load_preset_state()
    if state is None or not state.agent_id:
        checklist = await checks._build_checklist(
            agent_id=None,
            cron_job_id=None,
            delta_cron_job_id=None,
            maintain_cron_job_id=None,
        )
        return SecondBrainStatusResponse(applied=False, checklist=checklist)

    profile = await AgentService.get_agent_by_id(state.agent_id)
    if profile is None:
        logger.info(
            "Second Brain preset stored agent %s no longer exists; clearing preset config",
            state.agent_id,
        )
        await common._clear_preset_state()
        checklist = await checks._build_checklist(
            agent_id=None,
            cron_job_id=None,
            delta_cron_job_id=None,
            maintain_cron_job_id=None,
        )
        return SecondBrainStatusResponse(applied=False, checklist=checklist)

    maintain_cron_job_id = state.maintain_cron_job_id
    if maintain_cron_job_id is None:
        locale = common._normalize_locale(accept_language)
        maintain_cron_job_id, _ = await cron_setup._ensure_wiki_maintain_cron(
            agent_id=state.agent_id,
            locale=locale,
        )
        if maintain_cron_job_id:
            await common._save_preset_state(state.model_copy(update={"maintain_cron_job_id": maintain_cron_job_id}))

    checklist = await checks._build_checklist(
        agent_id=state.agent_id,
        cron_job_id=state.cron_job_id,
        delta_cron_job_id=state.delta_cron_job_id,
        maintain_cron_job_id=maintain_cron_job_id,
    )
    return SecondBrainStatusResponse(
        applied=True,
        agent_id=state.agent_id,
        agent_name=state.agent_name,
        cron_job_id=state.cron_job_id,
        delta_cron_job_id=state.delta_cron_job_id,
        maintain_cron_job_id=maintain_cron_job_id,
        applied_at=state.applied_at,
        checklist=checklist,
    )
