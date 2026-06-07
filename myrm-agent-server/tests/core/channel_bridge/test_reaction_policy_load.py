"""Tests for channel reaction policy loading from persisted channels config."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router_models import ReactionPolicy
from app.channels.types import ReactionLevel
from app.core.channel_bridge import channel_gateway
from app.core.channel_bridge.setup import _load_reaction_policy, refresh_reaction_policy


@pytest.mark.asyncio
async def test_load_reaction_policy_returns_defaults_when_db_empty() -> None:
    with patch(
        "app.core.channel_bridge.credential_spec.load_from_db",
        new=AsyncMock(return_value=None),
    ):
        policy = await _load_reaction_policy()

    assert policy == ReactionPolicy()


@pytest.mark.asyncio
async def test_load_reaction_policy_reads_all_emoji_fields() -> None:
    creds = {
        "reactionLevel": "simple",
        "processingEmoji": "🤔",
        "completionEmoji": "🎉",
        "failureEmoji": "⚠️",
    }
    with patch(
        "app.core.channel_bridge.credential_spec.load_from_db",
        new=AsyncMock(return_value=creds),
    ):
        policy = await _load_reaction_policy()

    assert policy.level == ReactionLevel.SIMPLE
    assert policy.processing_emoji == "🤔"
    assert policy.completion_emoji == "🎉"
    assert policy.failure_emoji == "⚠️"


@pytest.mark.asyncio
async def test_load_reaction_policy_ignores_blank_failure_emoji() -> None:
    creds = {
        "failureEmoji": "   ",
        "completionEmoji": "👍",
    }
    with patch(
        "app.core.channel_bridge.credential_spec.load_from_db",
        new=AsyncMock(return_value=creds),
    ):
        policy = await _load_reaction_policy()

    assert policy.failure_emoji == ReactionPolicy().failure_emoji
    assert policy.completion_emoji == "👍"


@pytest.mark.asyncio
async def test_refresh_reaction_policy_applies_to_gateway_router() -> None:
    custom = ReactionPolicy(failure_emoji="⚠️", completion_emoji="🎉")
    mock_router = MagicMock()

    with (
        patch.object(channel_gateway, "_router", mock_router),
        patch(
            "app.core.channel_bridge.setup._load_reaction_policy",
            new=AsyncMock(return_value=custom),
        ),
    ):
        await refresh_reaction_policy()

    mock_router.set_reaction_policy.assert_called_once_with(custom)
