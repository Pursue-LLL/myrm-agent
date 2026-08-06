"""Cron ↔ workflow template binding queries — server adapter.

[INPUT]
- app.core.cron.adapters.setup::get_cron_manager (POS: CronManager singleton)

[OUTPUT]
- count_cron_jobs_bound_to_template

[POS]
Read-only counts for workflow template library delete confirmations.
"""

from __future__ import annotations

_CRON_USER_ID = "default"


async def count_cron_jobs_bound_to_template(template_id: str) -> int:
    """Return how many Cron jobs reference ``template_id``."""
    normalized = template_id.strip()
    if not normalized:
        return 0

    from app.core.cron.adapters.setup import get_cron_manager

    mgr = get_cron_manager()
    jobs = await mgr.list_jobs(_CRON_USER_ID)
    return sum(
        1
        for job in jobs
        if (job.workflow_template_id or "").strip() == normalized
    )
