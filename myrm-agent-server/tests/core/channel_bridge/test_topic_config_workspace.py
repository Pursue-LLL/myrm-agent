"""Tests for topic workspace fields in SqlTopicManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.channel_bridge.topic_config import SqlTopicManager


@pytest.mark.asyncio
async def test_bind_topic_stores_project_id() -> None:
    manager = SqlTopicManager()
    saved: dict[str, object] = {}

    async def fake_save(channel: str, config: dict[str, object]) -> None:
        saved["config"] = config

    with (
        patch.object(manager, "_load_config", new=AsyncMock(return_value={})),
        patch.object(manager, "_save_config", side_effect=fake_save),
        patch(
            "app.core.channel_bridge.topic_workspace_bind.assert_project_workspace",
            new=AsyncMock(),
        ),
    ):
        ctx = await manager.bind_topic(
            "telegram",
            "chat-1",
            None,
            project_id="proj-1",
        )

    assert ctx.project_id == "proj-1"
    config = saved["config"]
    assert isinstance(config, dict)
    group = config["chat-1"]
    assert isinstance(group, dict)
    entry = group["__channel__"]
    assert isinstance(entry, dict)
    assert entry["projectId"] == "proj-1"
    assert "authorizedPath" not in entry


@pytest.mark.asyncio
async def test_bind_topic_rejects_dual_workspace() -> None:
    manager = SqlTopicManager()

    with pytest.raises(ValueError, match="mutually exclusive"):
        await manager.bind_topic(
            "telegram",
            "chat-1",
            None,
            project_id="proj-1",
            authorized_path="/tmp/vault",
        )
