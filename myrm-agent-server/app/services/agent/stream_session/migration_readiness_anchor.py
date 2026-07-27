"""Migration readiness first-turn outcome anchor persistence.

[INPUT]
- app.services.agent.params::AgentRequest (POS: migration_readiness_anchor field)
- app.services.memory.import_sessions::MemoryImportSessionService (POS: save outcome)

[OUTPUT]
- resolve_first_turn_outcome: Classify outcome from finalization signals.
- record_migration_first_turn_outcome: Persist outcome to DB.

[POS]
One-shot anchor for first-turn migration readiness tracking.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.platform_utils import get_session_factory
from app.services.agent.params import AgentRequest
from app.services.memory.import_sessions import MemoryImportSessionService

logger = logging.getLogger(__name__)

FirstTurnOutcome = Literal["success", "failed", "no_output"]


def resolve_first_turn_outcome(*, had_fatal_error: bool, has_assistant_content: bool) -> FirstTurnOutcome:
    """Classify first-turn execution outcome from stream finalization signals."""

    if had_fatal_error:
        return "failed"
    if has_assistant_content:
        return "success"
    return "no_output"


async def record_migration_first_turn_outcome(
    *,
    request: AgentRequest,
    had_fatal_error: bool,
    has_assistant_content: bool,
) -> None:
    """Persist first-turn outcome for one-shot migration readiness anchor."""

    anchor = request.migration_readiness_anchor
    if anchor is None:
        return
    import_batch_id = anchor.import_batch_id.strip()
    if not import_batch_id:
        return

    outcome = resolve_first_turn_outcome(
        had_fatal_error=had_fatal_error,
        has_assistant_content=has_assistant_content,
    )
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            await MemoryImportSessionService(db).save_post_import_first_turn_outcome(
                import_batch_id=import_batch_id,
                readiness_status=anchor.readiness_status,
                outcome=outcome,
                had_fatal_error=had_fatal_error,
                chat_id=request.chat_id,
                message_id=request.message_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist migration first-turn outcome for batch %s: %s",
                import_batch_id,
                exc,
            )
