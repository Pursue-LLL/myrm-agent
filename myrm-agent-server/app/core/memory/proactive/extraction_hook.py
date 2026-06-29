"""Commitment extraction hook — triggers extraction after sessions.

[INPUT]
- myrm_agent_harness.toolkits.memory.proactive::{CommitmentExtractor, CommitmentConfig, CommitmentRecord, CommitmentDueWindow}
- app.core.memory.proactive.sqlite_store::SqlAlchemyCommitmentStore

[OUTPUT]
- run_commitment_extraction: Async function to extract and persist commitments.

[POS]
Server-layer integration point. Called as a background task after session
cleanup to extract implicit commitments from the conversation.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime

logger = logging.getLogger(__name__)

LLMFunc = Callable[[str, str], Awaitable[str]]

_TWELVE_HOURS_MS = 12 * 60 * 60 * 1000


async def run_commitment_extraction(
    messages: Sequence[dict[str, str]],
    llm_func: LLMFunc,
    *,
    agent_id: str,
    user_id: str,
    channel: str = "web",
    source_chat_id: str | None = None,
    timezone: str = "UTC",
) -> int:
    """Extract commitments from conversation and persist them.

    Returns the number of commitments created/updated.
    """
    from myrm_agent_harness.toolkits.memory.proactive import (
        CommitmentConfig,
        CommitmentDueWindow,
        CommitmentExtractor,
        CommitmentRecord,
    )

    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore

    config = CommitmentConfig()
    extractor = CommitmentExtractor(config=config)
    store = SqlAlchemyCommitmentStore()

    now_ms = int(time.time() * 1000)
    expire_after_ms = config.expire_after_hours * 3600 * 1000
    await store.expire_stale(now_ms, expire_after_ms)

    existing = await store.list_pending(
        agent_id=agent_id,
        user_id=user_id,
        now_ms=now_ms,
        limit=8,
    )
    existing_for_prompt = [
        {
            "kind": c.kind.value,
            "reason": c.reason,
            "dedupe_key": c.dedupe_key,
        }
        for c in existing
    ]

    candidates = await extractor.extract(
        list(messages),
        llm_func,
        existing_pending=existing_for_prompt,
        timezone=timezone,
    )

    if not candidates:
        return 0

    created = 0
    for c in candidates:
        earliest_ms = _parse_iso_to_ms(c.due_window_earliest)
        if earliest_ms is None:
            continue

        latest_raw = _parse_iso_to_ms(c.due_window_latest) if c.due_window_latest else None
        latest_ms = latest_raw if latest_raw and latest_raw >= earliest_ms else earliest_ms + _TWELVE_HOURS_MS

        record = CommitmentRecord(
            agent_id=agent_id,
            user_id=user_id,
            channel=channel,
            kind=c.kind,
            sensitivity=c.sensitivity,
            reason=c.reason,
            suggested_text=c.suggested_text,
            dedupe_key=c.dedupe_key,
            confidence=c.confidence,
            due_window=CommitmentDueWindow(
                earliest_ms=earliest_ms,
                latest_ms=latest_ms,
                timezone=c.due_window_timezone or timezone,
            ),
            source_chat_id=source_chat_id,
        )

        try:
            await store.upsert(record)
            created += 1
        except Exception as e:
            logger.warning("Failed to persist commitment: %s", e)

    if created:
        logger.info(
            "Commitment extraction: %d candidates → %d persisted (agent=%s)",
            len(candidates),
            created,
            agent_id,
        )

    return created


def _parse_iso_to_ms(iso: str) -> int | None:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, AttributeError):
        return None
