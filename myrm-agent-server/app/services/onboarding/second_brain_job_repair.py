"""Bring a Second Brain wiki-delta job created before its capability fix up to the blueprint declaration.

[INPUT]
- app.core.cron.adapters.setup::get_cron_manager (POS: cron job CRUD)
- app.core.cron.blueprints::get_blueprint (POS: capability SSOT for the wiki_morning_delta job)
- app.services.wiki.vault::resolve_agent_wiki_vault_path (POS: vault root of the job's agent)

[OUTPUT]
- repair_wiki_delta_job(): patch a job that still carries the superseded declaration; True when patched

[POS]
Idempotent startup repair. It only touches a job whose capabilities equal the superseded declaration,
so declarations the user edited are never overwritten.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.cron.types import CronJobPatch, JobType

from app.core.cron.adapters.setup import get_cron_manager
from app.core.cron.blueprints import get_blueprint
from app.services.wiki.vault import resolve_agent_wiki_vault_path

logger = logging.getLogger(__name__)

_BLUEPRINT_ID = "wiki_morning_delta"
# The declaration shipped before wiki tools were gated by knowledge_* permissions: every wiki call was denied.
_SUPERSEDED_CAPABILITIES = frozenset({"file_read", "file_write"})


async def repair_wiki_delta_job(job_id: str, *, user_id: str) -> bool:
    """Declare the wiki capabilities and vault access the job's prompt relies on."""
    mgr = get_cron_manager()
    job = await mgr.get_job(job_id, user_id)
    if job is None or job.job_type != JobType.AGENT:
        return False
    if frozenset(job.required_capabilities) != _SUPERSEDED_CAPABILITIES:
        return False
    blueprint = get_blueprint(_BLUEPRINT_ID)
    if blueprint is None:
        return False

    allowed_roots = job.allowed_roots or (str(resolve_agent_wiki_vault_path(job.agent_id)),)
    await mgr.update_job(
        job_id,
        user_id,
        CronJobPatch(
            required_capabilities=blueprint.default_required_capabilities,
            allowed_roots=allowed_roots,
        ),
    )
    logger.info("Repaired wiki-delta cron job %s: declared wiki capabilities and vault access", job_id)
    return True
