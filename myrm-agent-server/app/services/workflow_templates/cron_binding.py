"""Cron ↔ workflow template binding queries — server adapter.

[INPUT]
- app.core.cron.adapters.setup::get_cron_manager (POS: CronManager singleton)

[OUTPUT]
- count_cron_jobs_bound_to_template

[POS]
Read-only counts for workflow template library delete confirmations.
"""

from __future__ import annotations

import logging
import sqlite3

from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError

logger = logging.getLogger(__name__)

_CRON_USER_ID = "default"


async def count_cron_jobs_bound_to_template(template_id: str) -> int:
    """Return how many Cron jobs reference ``template_id``."""
    normalized = template_id.strip()
    if not normalized:
        return 0

    from app.core.cron.adapters.setup import get_cron_manager

    mgr = get_cron_manager()
    try:
        jobs = await mgr.list_jobs(_CRON_USER_ID)
    except (SQLAlchemyOperationalError, sqlite3.OperationalError) as exc:
        # Stale dev DB may lack workflow_template_id until migrations run on restart.
        logger.warning(
            "Cron binding count unavailable for template %s: %s",
            normalized,
            exc,
        )
        return 0
    return sum(
        1
        for job in jobs
        if (job.workflow_template_id or "").strip() == normalized
    )
