"""Channel bind policy on SqlTopicManager.bind_topic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge.topic_config import (
    SEARCH_AGENT_CHANNEL_BIND_MSG,
    SqlTopicManager,
    is_search_agent_channel_bind_error,
)


def test_is_search_agent_channel_bind_error() -> None:
    assert is_search_agent_channel_bind_error(ValueError(SEARCH_AGENT_CHANNEL_BIND_MSG))
    assert not is_search_agent_channel_bind_error(ValueError("Agent not found: x"))


@pytest.mark.asyncio
async def test_bind_topic_rejects_search_agent() -> None:
    manager = SqlTopicManager()
    search_agent = MagicMock(
        id="builtin-fast-search", metadata={"prompt_mode": "search"}
    )

    with (
        patch.object(
            manager,
            "_resolve_agent_id",
            new_callable=AsyncMock,
            return_value="builtin-fast-search",
        ),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=search_agent,
        ),
        patch.object(manager, "_upsert_topic", new_callable=AsyncMock) as mock_upsert,
    ):
        with pytest.raises(ValueError, match=SEARCH_AGENT_CHANNEL_BIND_MSG):
            await manager.bind_topic(
                "telegram", "chat-1", None, agent_id="builtin-fast-search"
            )

    mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_bind_topic_rejects_deep_search_agent() -> None:
    manager = SqlTopicManager()
    search_agent = MagicMock(
        id="builtin-deep-search", metadata={"prompt_mode": "search"}
    )

    with (
        patch.object(
            manager,
            "_resolve_agent_id",
            new_callable=AsyncMock,
            return_value="builtin-deep-search",
        ),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=search_agent,
        ),
        patch.object(manager, "_upsert_topic", new_callable=AsyncMock) as mock_upsert,
    ):
        with pytest.raises(ValueError, match=SEARCH_AGENT_CHANNEL_BIND_MSG):
            await manager.bind_topic(
                "telegram", "chat-1", None, agent_id="builtin-deep-search"
            )

    mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_bind_topic_allows_general_agent() -> None:
    manager = SqlTopicManager()
    general_agent = MagicMock(id="general-1", metadata={"prompt_mode": "full"})

    with (
        patch.object(
            manager,
            "_resolve_agent_id",
            new_callable=AsyncMock,
            return_value="general-1",
        ),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=general_agent,
        ),
        patch.object(manager, "_upsert_topic", new_callable=AsyncMock) as mock_upsert,
    ):
        ctx = await manager.bind_topic("telegram", "chat-1", None, agent_id="general-1")

    assert ctx.agent_id == "general-1"
    mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_topic_purges_search_agent_binding() -> None:
    manager = SqlTopicManager()
    config: dict[str, object] = {
        "chat-1": {
            "__channel__": {
                "agentId": "builtin-fast-search",
                "enabled": True,
                "boundAt": "2026-01-01T00:00:00+00:00",
                "lastActiveAt": "2026-01-01T00:00:00+00:00",
            },
        },
    }
    search_agent = MagicMock(
        id="builtin-fast-search", metadata={"prompt_mode": "search"}
    )

    with (
        patch.object(
            manager, "_load_config", new_callable=AsyncMock, return_value=config
        ),
        patch.object(manager, "_save_config", new_callable=AsyncMock) as mock_save,
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=search_agent,
        ),
    ):
        ctx = await manager.resolve_topic("telegram", "chat-1", None)

    assert ctx is None
    assert "chat-1" not in config
    mock_save.assert_called_once_with("telegram", config)


@pytest.mark.asyncio
async def test_get_all_topics_strips_search_bindings() -> None:
    manager = SqlTopicManager()
    config: dict[str, object] = {
        "chat-1": {
            "__channel__": {
                "agentId": "builtin-deep-search",
                "enabled": True,
                "boundAt": "2026-01-01T00:00:00+00:00",
            },
        },
        "chat-2": {
            "__channel__": {
                "agentId": "general-1",
                "enabled": True,
                "boundAt": "2026-01-01T00:00:00+00:00",
            },
        },
    }
    search_agent = MagicMock(
        id="builtin-deep-search", metadata={"prompt_mode": "search"}
    )
    general_agent = MagicMock(id="general-1", metadata={"prompt_mode": "full"})

    async def _get_agent(agent_id: str) -> MagicMock | None:
        if agent_id == "builtin-deep-search":
            return search_agent
        if agent_id == "general-1":
            return general_agent
        return None

    with (
        patch.object(
            manager, "_load_config", new_callable=AsyncMock, return_value=config
        ),
        patch.object(manager, "_save_config", new_callable=AsyncMock) as mock_save,
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            side_effect=_get_agent,
        ),
    ):
        result = await manager.get_all_topics("telegram")

    assert "chat-1" not in result
    assert "chat-2" in result
    mock_save.assert_called_once_with("telegram", config)


@pytest.mark.asyncio
async def test_bind_topic_rejects_missing_agent() -> None:
    manager = SqlTopicManager()

    with (
        patch.object(
            manager,
            "_resolve_agent_id",
            new_callable=AsyncMock,
            return_value="missing-agent",
        ),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch.object(manager, "_upsert_topic", new_callable=AsyncMock) as mock_upsert,
    ):
        with pytest.raises(ValueError, match="Agent not found: missing-agent"):
            await manager.bind_topic(
                "telegram", "chat-1", None, agent_id="missing-agent"
            )

    mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_topic_purges_missing_agent_binding() -> None:
    manager = SqlTopicManager()
    config: dict[str, object] = {
        "chat-1": {
            "__channel__": {
                "agentId": "deleted-agent",
                "enabled": True,
                "boundAt": "2026-01-01T00:00:00+00:00",
                "lastActiveAt": "2026-01-01T00:00:00+00:00",
            },
        },
    }

    with (
        patch.object(
            manager, "_load_config", new_callable=AsyncMock, return_value=config
        ),
        patch.object(manager, "_save_config", new_callable=AsyncMock) as mock_save,
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        ctx = await manager.resolve_topic("telegram", "chat-1", None)

    assert ctx is None
    assert "chat-1" not in config
    mock_save.assert_called_once_with("telegram", config)


def test_agent_is_search_track_metadata_edges() -> None:
    assert not SqlTopicManager._agent_is_search_track(MagicMock(metadata=None))
    assert not SqlTopicManager._agent_is_search_track(MagicMock(metadata="not-a-dict"))
    assert not SqlTopicManager._agent_is_search_track(
        MagicMock(metadata={"prompt_mode": "full"})
    )
    assert SqlTopicManager._agent_is_search_track(
        MagicMock(metadata={"prompt_mode": "search"})
    )


@pytest.mark.asyncio
async def test_sanitize_skips_malformed_binding_entries() -> None:
    manager = SqlTopicManager()
    config: dict[str, object] = {
        "bad-group": "not-a-dict",
        "chat-ok": {
            "bad-topic": "not-a-dict",
            "__channel__": {
                "agentId": "",
                "enabled": True,
            },
        },
    }

    with patch(
        "app.services.agent.agent_service.AgentService.get_agent_by_id",
        new_callable=AsyncMock,
    ) as mock_get:
        changed = await manager._sanitize_unbindable_bindings("telegram", config)

    assert changed is False
    mock_get.assert_not_called()
    assert config["chat-ok"]["__channel__"]["agentId"] == ""


@pytest.mark.asyncio
async def test_resolve_topic_keeps_general_agent_binding() -> None:
    manager = SqlTopicManager()
    config: dict[str, object] = {
        "chat-1": {
            "__channel__": {
                "agentId": "general-1",
                "enabled": True,
                "boundAt": "2026-01-01T00:00:00+00:00",
                "lastActiveAt": "2026-01-01T00:00:00+00:00",
            },
        },
    }
    general_agent = MagicMock(id="general-1", metadata={"prompt_mode": "full"})

    with (
        patch.object(
            manager, "_load_config", new_callable=AsyncMock, return_value=config
        ),
        patch.object(manager, "_touch_active", new_callable=AsyncMock),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=general_agent,
        ),
    ):
        ctx = await manager.resolve_topic("telegram", "chat-1", None)

    assert ctx is not None
    assert ctx.agent_id == "general-1"
    assert "chat-1" in config
