"""A channel reports an edit it could not make, so the router can send the text as a new message.

``MessageEffects.edit_placeholder`` replaces the placeholder with the final reply and falls back to a new message
only when the edit raises; ``MessageBus.edit_channel_message`` and the heartbeat and approval notices rely on the
same signal. A channel that logs the failure and returns instead makes the router believe the text was delivered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.dingtalk import DingTalkChannel
from app.channels.providers.discord import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig
from app.channels.providers.feishu import FeishuChannel
from app.channels.providers.feishu.sdk import FeishuClient
from app.channels.providers.googlechat import GoogleChatChannel
from app.channels.providers.matrix import MatrixChannel
from app.channels.providers.mattermost import MattermostChannel
from app.channels.providers.msteams import MSTeamsChannel
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import TelegramApiError
from app.channels.providers.wecom.aibot_channel import WeComAiBotChannel
from app.channels.providers.whatsapp import WhatsAppChannel
from app.channels.types import OutboundMessage
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN

_CHAT, _MESSAGE = "chat-1", "42"


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("PUT", "https://platform.example.com/messages/42")
    return httpx.HTTPStatusError("rejected", request=request, response=httpx.Response(status, request=request))


def _discord_rejects(status: int = 404) -> BaseChannel:
    channel = DiscordChannel(DiscordChannelConfig(bot_token="t", enable_gateway=True))
    messageable = MagicMock()
    messageable.fetch_message = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(status=status, reason="rejected"), "rejected")
    )
    channel._resolve_channel = AsyncMock(return_value=messageable)  # type: ignore[method-assign]
    return channel


def _discord_channel_unreachable() -> BaseChannel:
    channel = DiscordChannel(DiscordChannelConfig(bot_token="t", enable_gateway=True))
    channel._resolve_channel = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return channel


def _feishu_refuses() -> BaseChannel:
    channel = FeishuChannel(app_id="a", app_secret="s")
    client = AsyncMock(spec=FeishuClient)
    client.edit_message.return_value = False
    channel._client = client
    return channel


def _telegram_message_gone() -> BaseChannel:
    channel = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    channel._rich_send_available = False
    channel._rich_draft_available = False
    channel._client.edit_message_text = AsyncMock(  # type: ignore[method-assign]
        side_effect=TelegramApiError(400, "Bad Request: message to edit not found")
    )
    return channel


def _teams_refuses() -> BaseChannel:
    channel = MSTeamsChannel(app_id="a", app_password="p")
    channel._api.resolve_service_url = MagicMock(return_value="https://smba.example.com")  # type: ignore[method-assign]
    channel._api.update_activity = AsyncMock(return_value=False)  # type: ignore[method-assign]
    return channel


def _teams_has_no_service_url() -> BaseChannel:
    channel = MSTeamsChannel(app_id="a", app_password="p")
    channel._api.resolve_service_url = MagicMock(return_value=None)  # type: ignore[method-assign]
    return channel


def _google_chat_refuses(status: int = 404) -> BaseChannel:
    channel = GoogleChatChannel(service_account_json="")
    channel._api.update_message = AsyncMock(side_effect=_http_error(status))  # type: ignore[method-assign]
    return channel


def _matrix_refuses() -> BaseChannel:
    channel = MatrixChannel(homeserver="https://matrix.example.com", access_token="t")
    client = AsyncMock()
    client.send_message_event = AsyncMock(side_effect=RuntimeError("M_FORBIDDEN"))
    channel._client = client
    return channel


def _matrix_not_running() -> BaseChannel:
    return MatrixChannel(homeserver="https://matrix.example.com", access_token="t")


def _mattermost_refuses(status: int = 404) -> BaseChannel:
    channel = MattermostChannel(server_url="https://mm.example.com", access_token="t")
    channel._api.update_post = AsyncMock(side_effect=_http_error(status))  # type: ignore[method-assign]
    return channel


def _whatsapp_not_connected() -> BaseChannel:
    return WhatsAppChannel(auth_dir="/tmp/test_wa_edit_contract")


def _dingtalk_message_is_not_a_card() -> BaseChannel:
    return DingTalkChannel(app_key="k", app_secret="s")


def _wecom_stream_is_not_active() -> BaseChannel:
    return WeComAiBotChannel(bot_id="b", secret="s")


@dataclass(frozen=True)
class EditFailure:
    """A channel set up so that the platform does not take an edit of message ``42`` in chat ``chat-1``."""

    label: str
    build: Callable[[], BaseChannel]
    # DingTalk and WeCom finalize their streams through their own send path, which already reports failures.
    finalizes_through_edit: bool = True


_FAILURES = [
    EditFailure("discord message deleted", _discord_rejects),
    EditFailure("discord channel unreachable", _discord_channel_unreachable),
    EditFailure("feishu edit refused", _feishu_refuses),
    EditFailure("telegram message deleted", _telegram_message_gone),
    EditFailure("teams edit refused", _teams_refuses),
    EditFailure("teams service url unknown", _teams_has_no_service_url),
    EditFailure("google chat edit refused", _google_chat_refuses),
    EditFailure("matrix edit refused", _matrix_refuses),
    EditFailure("matrix not running", _matrix_not_running),
    EditFailure("mattermost edit refused", _mattermost_refuses),
    EditFailure("whatsapp not connected", _whatsapp_not_connected),
    EditFailure("dingtalk message is not a card", _dingtalk_message_is_not_a_card, finalizes_through_edit=False),
    EditFailure("wecom stream not active", _wecom_stream_is_not_active, finalizes_through_edit=False),
]


def _final_reply() -> OutboundMessage:
    return OutboundMessage(channel="any", recipient_id=_CHAT, content="The final answer", user_id="u1")


@pytest.mark.parametrize("failure", _FAILURES, ids=lambda failure: failure.label)
@pytest.mark.asyncio
async def test_a_failed_edit_raises(failure: EditFailure) -> None:
    channel = failure.build()

    with pytest.raises(ChannelSendError):
        await channel.edit_message(_CHAT, _MESSAGE, "progress")


@pytest.mark.parametrize("failure", [f for f in _FAILURES if f.finalizes_through_edit], ids=lambda failure: failure.label)
@pytest.mark.asyncio
async def test_a_failed_final_edit_raises(failure: EditFailure) -> None:
    channel = failure.build()

    with pytest.raises(ChannelSendError):
        await channel.edit_placeholder_message(_CHAT, _MESSAGE, _final_reply())


@pytest.mark.parametrize("status, retriable", [(404, False), (429, True), (503, True)])
@pytest.mark.parametrize("build", [_discord_rejects, _google_chat_refuses, _mattermost_refuses], ids=lambda b: b.__name__)
@pytest.mark.asyncio
async def test_a_rejected_edit_is_retried_only_when_a_retry_can_succeed(
    build: Callable[[int], BaseChannel], status: int, retriable: bool
) -> None:
    with pytest.raises(ChannelSendError) as excinfo:
        await build(status).edit_message(_CHAT, _MESSAGE, "progress")

    assert excinfo.value.status_code == status
    assert excinfo.value.retriable is retriable


@pytest.mark.parametrize(
    "build",
    [_feishu_refuses, _teams_refuses, _teams_has_no_service_url, _dingtalk_message_is_not_a_card, _wecom_stream_is_not_active],
    ids=lambda b: b.__name__,
)
@pytest.mark.asyncio
async def test_a_refusal_without_a_reason_is_not_retried(build: Callable[[], BaseChannel]) -> None:
    with pytest.raises(ChannelSendError) as excinfo:
        await build().edit_message(_CHAT, _MESSAGE, "progress")

    assert excinfo.value.retriable is False
