"""Configuration version control service for message filtering.

Tracks configuration changes with version history and supports rollback.
"""

import logging

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import MessageFilterConfig, MessageFilterConfigHistory

logger = logging.getLogger(__name__)


class ConfigVersionService:
    """Service for managing configuration version history.

    Usage:
        >>> async with get_session() as db:
        ...     service = ConfigVersionService(db)
        ...     await service.save_version(config, updated_by="admin@example.com")
        ...     history = await service.get_history(limit=10)
        ...     await service.rollback_to_version(version=5, updated_by="admin@example.com")
    """

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def save_version(self, config: MessageFilterConfig, updated_by: str | None = None) -> int:
        """Save current configuration as a new version.

        Args:
            config: Current configuration to save
            updated_by: User who made the change (for audit trail)

        Returns:
            Version number assigned to this snapshot
        """
        latest_version = await self._get_latest_version()
        new_version = (latest_version or 0) + 1

        config_snapshot = {
            "enabled": config.enabled,
            "pii_mode": config.pii_mode,
            "whitelist_api_keys": config.whitelist_api_keys,
            "audit_enabled": config.audit_enabled,
        }

        history_entry = MessageFilterConfigHistory(
            config=config_snapshot,
            updated_by=updated_by,
            version=new_version,
        )
        self._db.add(history_entry)
        await self._db.flush()

        logger.info(f"Saved config version {new_version} by {updated_by}")
        return new_version

    async def get_history(self, limit: int = 50, offset: int = 0) -> list[MessageFilterConfigHistory]:
        """Retrieve configuration history.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip (for pagination)

        Returns:
            List of configuration history entries, newest first
        """
        stmt = (
            select(MessageFilterConfigHistory).order_by(desc(MessageFilterConfigHistory.updated_at)).limit(limit).offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_version(self, version: int) -> MessageFilterConfigHistory | None:
        """Get a specific configuration version.

        Args:
            version: Version number to retrieve

        Returns:
            Configuration history entry, or None if not found
        """
        stmt = select(MessageFilterConfigHistory).where(MessageFilterConfigHistory.version == version)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def rollback_to_version(self, version: int, updated_by: str | None = None) -> MessageFilterConfig | None:
        """Rollback configuration to a previous version.

        Args:
            version: Version number to rollback to
            updated_by: User performing the rollback (for audit trail)

        Returns:
            Restored configuration, or None if version not found
        """
        history_entry = await self.get_version(version)
        if history_entry is None:
            logger.warning(f"Version {version} not found, rollback failed")
            return None

        stmt = select(MessageFilterConfig).limit(1)
        result = await self._db.execute(stmt)
        current_config = result.scalars().first()

        if current_config is None:
            current_config = MessageFilterConfig()
            self._db.add(current_config)

        current_config.enabled = history_entry.config["enabled"]
        current_config.pii_mode = history_entry.config["pii_mode"]
        current_config.whitelist_api_keys = history_entry.config["whitelist_api_keys"]
        current_config.audit_enabled = history_entry.config["audit_enabled"]
        current_config.updated_by = updated_by

        await self._db.flush()

        await self.save_version(current_config, updated_by=f"{updated_by} (rollback to v{version})")

        logger.info(f"Rolled back config to version {version} by {updated_by}")
        return current_config

    async def _get_latest_version(self) -> int | None:
        """Get the latest version number.

        Returns:
            Latest version number, or None if no history exists
        """
        stmt = select(MessageFilterConfigHistory.version).order_by(desc(MessageFilterConfigHistory.version)).limit(1)
        result = await self._db.execute(stmt)
        return result.scalar()
