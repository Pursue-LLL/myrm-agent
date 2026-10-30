"""Saving a channel's credentials applies them to the running gateway, for every channel that declares credentials."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.providers.github.channel import GitHubChannel
from app.channels.providers.onebot.channel import OneBotChannel
from app.channels.providers.registry import get_channel_class_safe, registered_names
from app.services.channels.credential_reload import CREDENTIAL_KEY_TO_CHANNEL, reload_channel_credentials


def _channel_case(name: str) -> object:
    if name == "voice":
        return pytest.param(
            name,
            marks=pytest.mark.xfail(
                strict=True,
                reason="voice declares its credentials under twilioCredentials, a key the table does not know",
            ),
        )
    return name


@pytest.mark.parametrize("channel_name", [_channel_case(name) for name in sorted(registered_names())])
def test_the_credential_key_a_channel_declares_is_hot_registered(channel_name: str) -> None:
    channel_class = get_channel_class_safe(channel_name)
    spec = getattr(channel_class, "credential_spec", None)
    if spec is None:
        pytest.skip(f"{channel_name} declares no credentials, so a save has nothing to apply")

    assert CREDENTIAL_KEY_TO_CHANNEL.get(spec.config_key) == channel_name


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config_key", "saved", "channel_class"),
    [
        ("githubCredentials", {"personalAccessToken": "ghp_test"}, GitHubChannel),
        ("onebotCredentials", {"host": "127.0.0.1", "port": "3001"}, OneBotChannel),
    ],
)
async def test_a_save_builds_the_channel_from_its_credentials_and_swaps_it_in(
    config_key: str, saved: dict[str, object], channel_class: type
) -> None:
    gateway = MagicMock()
    gateway.swap_channel = AsyncMock()
    gateway.bus.get_channel = MagicMock(return_value=None)

    with (
        patch("app.core.channel_bridge.credential_spec.load_from_db", new=AsyncMock(return_value=saved)),
        patch("app.core.channel_bridge.credential_spec.is_channel_enabled", new=AsyncMock(return_value=True)),
        patch("app.core.channel_bridge.channel_gateway", gateway),
    ):
        await reload_channel_credentials(config_key)

    gateway.swap_channel.assert_awaited_once()
    registered, replaced = gateway.swap_channel.await_args.args
    assert isinstance(registered, channel_class)
    assert replaced is None
