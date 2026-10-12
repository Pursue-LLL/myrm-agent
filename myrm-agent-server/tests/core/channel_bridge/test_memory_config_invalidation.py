from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.channel_bridge import config_cache


@pytest.mark.asyncio
async def test_await_memory_manager_config_invalidation_waits_for_shutdown() -> None:
    shutdown = AsyncMock()
    invalidate = AsyncMock()

    with (
        patch.object(config_cache, "_invalidate_platform_dedup_llm_cache_sync") as sync_inv,
        patch(
            "app.core.memory.adapters.setup.shutdown_cached_memory_managers",
            shutdown,
        ),
    ):
        sync_inv.side_effect = lambda: invalidate()
        await config_cache.await_memory_manager_config_invalidation()

    sync_inv.assert_called_once()
    shutdown.assert_awaited_once()
