"""[INPUT]
- .common (POS: shared constants and helpers)

[OUTPUT]
- ConfigStoreMixin

[POS]
Topic manager mixin: UserConfig read/write for topic maps with the in-process cache.
"""

from __future__ import annotations

import time

from .common import (
    _CACHE_TTL,
    logger,
)


class ConfigStoreMixin:
    async def _upsert_topic(
        self,
        channel: str,
        chat_id: str,
        storage_key: str,
        topic_entry: dict[str, object],
    ) -> None:
        config = await self._load_config(channel)

        group_topics = config.get(chat_id)
        if not isinstance(group_topics, dict):
            group_topics = {}
            config[chat_id] = group_topics

        group_topics[storage_key] = topic_entry
        await self._save_config(channel, config)

    async def _save_config(self, channel: str, config: dict[str, object]) -> None:
        try:
            from sqlalchemy import select

            from app.database.connection import get_session
            from app.database.models import UserConfig

            config_key = f"{channel}Topics"
            async with get_session() as session:
                result = await session.execute(
                    select(UserConfig).where(
                        UserConfig.config_key == config_key,
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    row.config_value = config
                else:
                    session.add(
                        UserConfig(
                            id=__import__("nanoid").generate(size=21),
                            config_key=config_key,
                            config_value=config,
                            version="1_0",
                            last_device_id="server",
                        )
                    )
                await session.commit()

            self._invalidate_cache(channel)
        except Exception as exc:
            logger.warning("SqlTopicManager: failed to save %s topics: %s", channel, exc)

    async def _load_config(self, channel: str) -> dict[str, object]:
        now = time.monotonic()
        cached_ts = self._cache_ts.get(channel, 0.0)
        if now - cached_ts < _CACHE_TTL and channel in self._cache:
            return self._cache[channel]

        try:
            from sqlalchemy import select

            from app.database.connection import get_session
            from app.database.models import UserConfig

            config_key = f"{channel}Topics"
            async with get_session() as session:
                result = await session.execute(
                    select(UserConfig.config_value).where(
                        UserConfig.config_key == config_key,
                    )
                )
                row = result.scalar_one_or_none()

            self._cache_ts[channel] = now
            data = row if isinstance(row, dict) else {}
            self._cache[channel] = data
            return data
        except Exception as exc:
            logger.warning("SqlTopicManager: failed to load %s topics: %s", channel, exc)
            return self._cache.get(channel, {})

    def _invalidate_cache(self, channel: str) -> None:
        self._cache.pop(channel, None)
        self._cache_ts.pop(channel, None)
