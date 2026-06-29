"""Pending follow-ups section for heartbeat situation reports.

[INPUT]
- myrm_agent_harness.toolkits.cron.situation::SituationContext
- app.core.memory.proactive.sqlite_store::SqlAlchemyCommitmentStore
- app.core.memory.proactive.delivery_tracker::{begin,register}_follow_up_*

[OUTPUT]
- PendingCommitmentsSection: SituationSection that lists due follow-ups.

[POS]
Heartbeat integration for proactive memory. Injects due follow-ups into the
situation report. Marks attempted on inject; SENT only after delivery ack.
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.toolkits.cron.situation import SituationContext

logger = logging.getLogger(__name__)


class PendingCommitmentsSection:
    """Lists due follow-ups for heartbeat context injection."""

    name = "Pending Follow-ups"
    priority = 5

    async def build(self, ctx: SituationContext) -> str | None:
        if not ctx.memory_enabled:
            return None

        from app.core.memory.proactive.delivery_tracker import register_follow_up_attempts
        from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore

        store = SqlAlchemyCommitmentStore()
        now_ms = int(time.time() * 1000)

        due = await store.list_due(
            agent_id=ctx.agent_id,
            user_id=ctx.user_id,
            now_ms=now_ms,
            limit=3,
        )

        if not due:
            return None

        lines: list[str] = []
        for c in due:
            sensitivity_tag = f" [{c.sensitivity.value}]" if c.sensitivity.value != "routine" else ""
            lines.append(f"- {c.suggested_text}{sensitivity_tag} (reason: {c.reason})")

        due_ids = [c.id for c in due]
        register_follow_up_attempts(due_ids)
        try:
            await store.mark_attempted(due_ids, now_ms)
        except Exception:
            logger.warning("Failed to mark %d follow-ups as attempted", len(due_ids), exc_info=True)

        return "\n".join(lines)
