"""Pending commitments section for heartbeat situation reports.

[INPUT]
- myrm_agent_harness.toolkits.cron.situation::SituationContext
- app.core.commitment.sqlite_store::SqlAlchemyCommitmentStore

[OUTPUT]
- PendingCommitmentsSection: SituationSection that lists due commitments.

[POS]
Heartbeat integration for the commitment system. Injects due commitments
into the situation report so the agent can proactively follow up.
Marks injected commitments as sent to prevent repeated delivery.
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.toolkits.cron.situation import SituationContext

logger = logging.getLogger(__name__)


class PendingCommitmentsSection:
    """Lists due commitments for heartbeat context injection.

    After building the section text, marks all injected commitments
    as 'sent' so they are not re-delivered on subsequent heartbeats.
    """

    name = "Pending Follow-ups"
    priority = 5

    async def build(self, ctx: SituationContext) -> str | None:
        from myrm_agent_harness.toolkits.commitment.types import CommitmentStatus

        from app.core.commitment.sqlite_store import SqlAlchemyCommitmentStore

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
        try:
            await store.mark_attempted(due_ids, now_ms)
            await store.mark_status(due_ids, CommitmentStatus.SENT, now_ms)
        except Exception:
            logger.warning("Failed to mark %d commitments as sent", len(due_ids), exc_info=True)

        return "\n".join(lines)
