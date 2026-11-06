"""[INPUT]
- .common (POS: shared constants and preset state)

[OUTPUT]
- _maybe_enable_wiki_gmail_source, _apply_success_message, _rollback_apply

[POS]
Second Brain preset: agent skill/vault mutations and the apply rollback.
"""

from __future__ import annotations

from app.services.agent.agent_service import AgentService

from . import common
from .common import (
    _USER_ID,
    _ApplyMutation,
    logger,
)


async def _maybe_enable_wiki_gmail_source() -> None:
    from app.services.wiki.source_sync.defaults import (
        maybe_enable_wiki_gmail_on_google_connect,
    )

    await maybe_enable_wiki_gmail_on_google_connect(respect_existing_config=False)


def _apply_success_message(*, locale: str, vault_files_seeded: int) -> str:
    if vault_files_seeded > 0:
        if locale == "en":
            return f"Second Brain preset applied; synced {vault_files_seeded} wiki files"
        return f"第二大脑预设已应用，已同步 {vault_files_seeded} 个 wiki 文件"
    if locale == "en":
        return "Second Brain preset applied successfully"
    return "第二大脑预设已应用"


async def _rollback_apply(mutation: _ApplyMutation) -> None:
    if mutation.created_cron_job_ids:
        mgr = common.get_cron_manager()
        for cron_job_id in mutation.created_cron_job_ids:
            try:
                await mgr.delete_job(cron_job_id, _USER_ID)
            except Exception as exc:
                logger.warning("Rollback failed to delete cron job %s: %s", cron_job_id, exc)
    if mutation.created_agent_id:
        try:
            await AgentService.delete_agent(mutation.created_agent_id)
        except Exception as exc:
            logger.warning("Rollback failed to delete agent %s: %s", mutation.created_agent_id, exc)
