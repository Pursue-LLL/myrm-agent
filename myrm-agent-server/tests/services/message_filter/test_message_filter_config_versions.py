"""Configuration snapshots carry only the switches the filter pipeline reads."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import MessageFilterConfig, MessageFilterConfigHistory
from app.services.message_filter import ConfigVersionService


async def test_a_saved_snapshot_carries_no_pii_mode(db_session: AsyncSession) -> None:
    config = MessageFilterConfig(enabled=False, whitelist_api_keys=["sk-allowed"], audit_enabled=False)
    db_session.add(config)
    await db_session.flush()

    version = await ConfigVersionService(db_session).save_version(config, updated_by="admin")

    entry = await ConfigVersionService(db_session).get_version(version)
    assert entry is not None
    assert entry.config == {"enabled": False, "whitelist_api_keys": ["sk-allowed"], "audit_enabled": False}


async def test_a_snapshot_stored_with_pii_mode_still_rolls_back(db_session: AsyncSession) -> None:
    db_session.add(
        MessageFilterConfigHistory(
            config={"enabled": False, "pii_mode": "block", "whitelist_api_keys": ["sk-allowed"], "audit_enabled": False},
            updated_by="legacy",
            version=1,
        )
    )
    await db_session.flush()

    restored = await ConfigVersionService(db_session).rollback_to_version(1, updated_by="admin")

    assert restored is not None
    assert (restored.enabled, restored.whitelist_api_keys, restored.audit_enabled) == (False, ["sk-allowed"], False)
