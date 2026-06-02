"""Database-backed ConfigManager for hot-reloading filter configurations."""

import logging
from collections.abc import Callable

from myrm_agent_harness.agent.security.message_filtering import FilterConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import MessageFilterConfig

logger = logging.getLogger(__name__)

ConfigObserver = Callable[[FilterConfig], None]


class DatabaseConfigManager:
    """Database-backed configuration manager with hot-reload support.

    Usage:
        >>> async with get_session() as db:
        ...     manager = DatabaseConfigManager(db)
        ...     manager.subscribe(lambda cfg: print(f"Config changed: {cfg}"))
        ...     await manager.reload()  # Load from DB
        ...     config = await manager.get_config()
    """

    def __init__(self, db_session: AsyncSession):
        self._db = db_session
        self._config: FilterConfig | None = None
        self._observers: list[ConfigObserver] = []

    async def get_config(self) -> FilterConfig:
        """Get current configuration, loading from DB if not cached.

        Returns:
            Current filter configuration
        """
        if self._config is None:
            await self.reload()
        return self._config or FilterConfig()

    async def reload(self) -> None:
        """Reload configuration from database.

        Fetches latest config from DB and notifies observers if changed.
        """
        try:
            stmt = select(MessageFilterConfig).limit(1)
            result = await self._db.execute(stmt)
            db_config = result.scalars().first()

            if db_config is None:
                logger.warning("No config found in DB, using defaults")
                new_config = FilterConfig()
            else:
                new_config = FilterConfig(
                    enabled=db_config.enabled,
                    whitelist_api_keys=set(db_config.whitelist_api_keys),
                    audit_enabled=db_config.audit_enabled,
                )

            if self._config != new_config:
                logger.info(f"Config reloaded: {self._config} -> {new_config}")
                self._config = new_config
                self._notify_observers()
            else:
                logger.debug("Config unchanged after reload")

        except Exception as e:
            logger.error(f"Failed to reload config from DB: {e}", exc_info=True)
            if self._config is None:
                logger.warning("Using default config as fallback")
                self._config = FilterConfig()

    def subscribe(self, observer: ConfigObserver) -> None:
        """Subscribe to configuration changes.

        Args:
            observer: Callback function invoked when config changes
        """
        self._observers.append(observer)

    def _notify_observers(self) -> None:
        """Notify all observers of configuration change."""
        for observer in self._observers:
            try:
                observer(self._config)
            except Exception as e:
                logger.error(f"Observer callback failed: {e}", exc_info=True)
