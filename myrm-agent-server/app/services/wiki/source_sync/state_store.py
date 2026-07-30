"""Persist wiki source sync run state for UI observability."""

from __future__ import annotations

import json
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import UserConfig
from app.services.wiki.source_sync.schemas import WikiSourceSyncRunSummary, WikiSourceSyncState

logger = logging.getLogger(__name__)

STATE_KEY = "wikiSourceSyncState"


async def load_wiki_source_sync_state(db: AsyncSession) -> WikiSourceSyncState:
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == STATE_KEY))
    ).scalars().first()
    if row is None:
        return WikiSourceSyncState()
    raw = row.config_value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid wikiSourceSyncState JSON; using defaults")
            return WikiSourceSyncState()
    if not isinstance(raw, dict):
        return WikiSourceSyncState()
    try:
        return WikiSourceSyncState.model_validate(raw)
    except ValidationError as exc:
        logger.warning("Invalid wikiSourceSyncState schema: %s", exc)
        return WikiSourceSyncState()


async def save_wiki_source_sync_state(db: AsyncSession, state: WikiSourceSyncState) -> WikiSourceSyncState:
    payload = state.model_dump(mode="json")
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == STATE_KEY))
    ).scalars().first()
    if row:
        row.config_value = payload
        row.is_encrypted = False
        flag_modified(row, "config_value")
    else:
        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key=STATE_KEY,
                config_value=payload,
                is_encrypted=False,
            )
        )
    await db.commit()
    return state


def state_from_run_summary(summary: WikiSourceSyncRunSummary) -> WikiSourceSyncState:
    from datetime import UTC, datetime

    from app.services.wiki.source_sync.schemas import WikiSourceSyncSourceState

    errors: list[str] = []
    sources: list[WikiSourceSyncSourceState] = []
    for item in summary.results:
        sources.append(
            WikiSourceSyncSourceState(
                source=item.source,
                published=item.published,
                skipped=item.skipped,
                failed=item.failed,
                errors=item.errors[:5],
            )
        )
        for err in item.errors:
            if len(errors) >= 20:
                break
            errors.append(f"{item.source}: {err}")

    return WikiSourceSyncState(
        last_sync_at=datetime.now(UTC),
        last_errors=errors,
        sources=sources,
        total_published=summary.total_published,
        total_skipped=summary.total_skipped,
        total_failed=summary.total_failed,
    )
