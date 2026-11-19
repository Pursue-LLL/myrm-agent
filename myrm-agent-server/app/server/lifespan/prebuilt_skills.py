"""[INPUT]
- app.core.skills.prebuilt_sync (POS: bundled seeds -> storage reconciliation)
- app.config.deploy_mode::is_local_mode (POS: local versus sandbox deployment)
- app.core.skills.store.service::skills_service (POS: per-user enablement of prebuilt skills)
- app.api.health.update_status::note_prebuilt_sync_result (POS: the update panel's summary of this start's sync)

[OUTPUT]
- init_prebuilt_skills (boot step), verify_prebuilt_skills (warm-up step)

[POS]
The two halves of the prebuilt skill sync in the server lifespan.
The boot step makes the bundled skills available before uvicorn binds. In local mode it reuses the last complete sync
when the bundled seeds are unchanged and every stored copy is present, which spares the single event loop the parse,
hash and write work of a reconciliation before the first screen; any other start (first run, an update that changed a
seed, a missing copy) reconciles in full first.
The warm-up step runs the full reconciliation a reusing start skipped, once the first screen has loaded, so what storage
holds is checked against the seeds at every start just as before, only later.
Imports stay inside the functions: this module is imported by the lifespan, whose import cost counts against the boot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.skills.prebuilt_sync import PrebuiltSyncResult


async def _publish(sync_result: PrebuiltSyncResult) -> None:
    """Report a reconciliation's outcome to the update panel and align the user's skill enablement with its skills."""
    from app.api.health.update_status import note_prebuilt_sync_result
    from app.core.skills.store.service import skills_service

    note_prebuilt_sync_result(sync_result.synced_count)
    if sync_result.skill_ids:
        await skills_service.user_config.ensure_prebuilt_enabled_after_sync(list(sync_result.skill_ids))


async def init_prebuilt_skills() -> None:
    """Make the bundled skills available before the server accepts requests."""
    from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

    from app.config.deploy_mode import is_local_mode
    from app.core.skills.prebuilt_sync import sync_prebuilt_seeds

    await _publish(await sync_prebuilt_seeds(get_storage_provider(), reuse_unchanged=is_local_mode()))


async def verify_prebuilt_skills() -> None:
    """Run the reconciliation a reusing boot skipped; nothing to do when the boot reconciled in full."""
    from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

    from app.core.skills.prebuilt_sync import verify_reused_sync

    result = await verify_reused_sync(get_storage_provider())
    if result is not None and result.synced_count:
        await _publish(result)
