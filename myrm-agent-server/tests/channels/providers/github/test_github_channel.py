"""GitHubChannel outbound tests — render multi-chunk comment delivery."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channels.providers.github.channel import GitHubChannel
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
            mock_post.return_value = True
            result = await ch.send(msg)

        assert mock_post.await_count == len(expected_chunks)
        for i, call in enumerate(mock_post.await_args_list):
            assert call.args[3] == expected_chunks[i]
        assert result == "gh-comment-owner/repo-42"
