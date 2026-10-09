"""GitHubChannel outbound tests — render multi-chunk comment delivery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.github.channel import GitHubChannel
from app.channels.providers.github.helpers import post_issue_comment
from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage


def _make_channel() -> GitHubChannel:
    ch = GitHubChannel()
    ch._token = "ghp_test"
    return ch


class TestGitHubSend:
    @pytest.mark.asyncio
    async def test_send_posts_each_render_chunk(self) -> None:
        ch = _make_channel()
        long_body = "GitHub issue reply body.\n" * 4000
        msg = OutboundMessage(
            channel="github",
            recipient_id="owner/repo#42",
            content=long_body,
            user_id="u1",
        )
        expected_chunks = render(msg, ch.render_style)
        assert len(expected_chunks) >= 2

        with patch(
            "app.channels.providers.github.channel.post_issue_comment",
            new_callable=AsyncMock,
        ) as mock_post:
            result = await ch.send(msg)

        assert mock_post.await_count == len(expected_chunks)
        for i, call in enumerate(mock_post.await_args_list):
            assert call.args[3] == expected_chunks[i]
        assert result == "gh-comment-owner/repo-42"

    @pytest.mark.asyncio
    async def test_comment_github_refused_is_raised_not_swallowed(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="github", recipient_id="owner/repo#42", content="reply", user_id="u1")
        refused = ChannelSendError.from_http_status("github", 403, "Resource not accessible")

        with patch("app.channels.providers.github.channel.post_issue_comment", AsyncMock(side_effect=refused)):
            with pytest.raises(ChannelSendError) as excinfo:
                await ch.send(msg)

        assert excinfo.value is refused
        assert ch.health.last_error

    @pytest.mark.asyncio
    async def test_missing_token_is_a_permanent_failure(self) -> None:
        ch = GitHubChannel()
        msg = OutboundMessage(channel="github", recipient_id="owner/repo#42", content="reply", user_id="u1")

        with pytest.raises(ChannelSendError) as excinfo:
            await ch.send(msg)

        assert excinfo.value.retriable is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("recipient", ["", "owner/repo", "owner/repo#x"])
    async def test_recipient_that_is_not_an_issue_is_a_permanent_failure(self, recipient: str) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="github", recipient_id=recipient, content="reply", user_id="u1")

        with pytest.raises(ChannelSendError) as excinfo:
            await ch.send(msg)

        assert excinfo.value.retriable is False


class TestPostIssueComment:
    @staticmethod
    def _client(response: httpx.Response | Exception) -> MagicMock:
        client = MagicMock()
        client.post = AsyncMock(side_effect=response) if isinstance(response, Exception) else AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        return client

    @pytest.mark.asyncio
    async def test_created_comment_returns_quietly(self) -> None:
        with patch("httpx.AsyncClient", return_value=self._client(httpx.Response(201))):
            assert await post_issue_comment("tok", "owner/repo", 1, "hi") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("status", "retriable"), [(404, False), (422, False), (429, True), (502, True)])
    async def test_rejection_is_classified_by_status(self, status: int, retriable: bool) -> None:
        with patch("httpx.AsyncClient", return_value=self._client(httpx.Response(status, text="nope"))):
            with pytest.raises(ChannelSendError) as excinfo:
                await post_issue_comment("tok", "owner/repo", 1, "hi")

        assert (excinfo.value.status_code, excinfo.value.retriable) == (status, retriable)

    @pytest.mark.asyncio
    async def test_transport_failure_may_be_retried(self) -> None:
        with patch("httpx.AsyncClient", return_value=self._client(httpx.ConnectError("down"))):
            with pytest.raises(ChannelSendError) as excinfo:
                await post_issue_comment("tok", "owner/repo", 1, "hi")

        assert excinfo.value.retriable is True
