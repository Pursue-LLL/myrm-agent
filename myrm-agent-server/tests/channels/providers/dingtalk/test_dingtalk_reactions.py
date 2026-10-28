"""DingTalk reaction (robot emotion) endpoints.

DingTalk exposes the robot emotion API at ``/v1.0/robot/emotion/{reply,recall}`` (singular); a
request to any other path is answered with an HTTP error that the channel only logs, so the
reaction silently never appears.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.dingtalk import DingTalkChannel


def _channel_with_http(status_code: int = 200) -> tuple[DingTalkChannel, AsyncMock]:
    ch = DingTalkChannel(app_key="test_key", app_secret="test_secret", robot_code="robot1")
    ch._api._access_token = "mock_token"
    ch._api._token_expires_at = 9999999999.0
    post = AsyncMock(return_value=MagicMock(status_code=status_code, text="denied"))
    ch._api._http = MagicMock(post=post)
    return ch, post


class TestEmotionEndpoints:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "action"),
        [pytest.param("send_emotion", "reply", id="add"), pytest.param("recall_emotion", "recall", id="remove")],
    )
    async def test_calls_use_the_singular_emotion_path(self, method: str, action: str) -> None:
        ch, post = _channel_with_http()
        await getattr(ch._api, method)("msg1", "conv1", "\U0001f440")
        assert post.await_args.args[0].endswith(f"/v1.0/robot/emotion/{action}")

    @pytest.mark.asyncio
    async def test_react_then_clear_hits_reply_then_recall(self) -> None:
        ch, post = _channel_with_http()
        await ch.react_to_message("conv1", "msg1", "\U0001f440")
        await ch.react_to_message("conv1", "msg1", "")
        paths = [call.args[0].rsplit("/", 1)[-1] for call in post.await_args_list]
        assert paths == ["reply", "recall"]


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_an_empty_emoji_recalls_the_glyph_that_was_added(self) -> None:
        ch, post = _channel_with_http()
        await ch.react_to_message("conv1", "msg1", "\U0001f440")
        await ch.react_to_message("conv1", "msg1", "")
        await ch.react_to_message("conv1", "msg1", "")
        assert len(post.await_args_list) == 2
        assert post.await_args_list[1].kwargs["json"]["emotionName"] == "\U0001f440"

    @pytest.mark.asyncio
    async def test_an_empty_emoji_calls_nothing_when_no_reaction_was_added(self) -> None:
        ch, post = _channel_with_http()
        await ch.react_to_message("conv1", "msg1", "")
        post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_refused_add_raises_with_the_status_and_is_not_remembered(self) -> None:
        ch, post = _channel_with_http(status_code=403)
        with pytest.raises(ChannelSendError, match="HTTP 403"):
            await ch.react_to_message("conv1", "msg1", "\U0001f440")
        await ch.react_to_message("conv1", "msg1", "")
        assert len(post.await_args_list) == 1

    @pytest.mark.asyncio
    async def test_a_message_without_a_conversation_is_skipped(self) -> None:
        ch, post = _channel_with_http()
        await ch.react_to_message("", "msg1", "\U0001f440")
        post.assert_not_awaited()
