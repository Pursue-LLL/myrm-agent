"""POST /generate-title passes the persisted privacy switch to the title generator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.chats.chat.title import generate_chat_title


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "expected"), [({"privacyEnabled": True}, True), ({"privacyEnabled": False}, False), ({}, False)]
)
async def test_generate_title_forwards_the_privacy_switch(settings: dict[str, object], expected: bool) -> None:
    configs = SimpleNamespace(providers_dict=None, personal_settings_dict=settings)
    generator = AsyncMock(return_value="标题")

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(return_value=configs)),
        patch("app.api.chats.chat.title.ChatService.generate_chat_title", new=generator),
    ):
        await generate_chat_title(SimpleNamespace(messages=[object()]))

    assert generator.call_args.kwargs["mask_pii"] is expected
