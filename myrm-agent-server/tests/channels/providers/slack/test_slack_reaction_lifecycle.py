"""Slack removes a reaction through ``reactions.remove`` and says why a reaction call failed.

``reactions.add`` / ``reactions.remove`` answer HTTP 200 with ``ok: false``; the old client logged
that at debug and returned, so a missing ``reactions:write`` scope looked like a working bot.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from tests.channels.providers.slack.test_slack_channel import _make_channel, _ok_json

EYES = "\U0001f440"


def _error(error: str, **extra: object) -> httpx.Response:
    return httpx.Response(200, json={"ok": False, "error": error, **extra})


def _methods(post: AsyncMock) -> list[str]:
    return [call.args[0].rsplit("/", 1)[-1] for call in post.await_args_list]


@pytest.mark.asyncio
async def test_an_empty_emoji_removes_the_reaction_that_was_added() -> None:
    ch = _make_channel()
    with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as post:
        await ch.react_to_message("C1", "1700000000.000100", EYES)
        await ch.react_to_message("C1", "1700000000.000100", "")

    assert _methods(post) == ["reactions.add", "reactions.remove"]
    assert post.await_args_list[1].kwargs["json"] == {"channel": "C1", "timestamp": "1700000000.000100", "name": "eyes"}


@pytest.mark.asyncio
async def test_an_empty_emoji_calls_nothing_when_no_reaction_was_added() -> None:
    ch = _make_channel()
    with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as post:
        await ch.react_to_message("C1", "1700000000.000100", "")
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_reaction_is_removed_only_once() -> None:
    ch = _make_channel()
    with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as post:
        await ch.react_to_message("C1", "1.1", EYES)
        await ch.react_to_message("C1", "1.1", "")
        await ch.react_to_message("C1", "1.1", "")
    assert _methods(post) == ["reactions.add", "reactions.remove"]


@pytest.mark.asyncio
async def test_a_missing_scope_is_raised_with_the_scope_that_is_needed() -> None:
    ch = _make_channel()
    response = _error("missing_scope", needed="reactions:write", provided="chat:write")
    with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=response):
        with pytest.raises(ChannelSendError, match=r"missing_scope.*reactions:write"):
            await ch.react_to_message("C1", "1.1", EYES)


@pytest.mark.asyncio
async def test_a_failed_add_is_not_remembered_so_nothing_is_removed_later() -> None:
    ch = _make_channel()
    with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_error("invalid_name")) as post:
        with pytest.raises(ChannelSendError, match="invalid_name"):
            await ch.react_to_message("C1", "1.1", EYES)
        await ch.react_to_message("C1", "1.1", "")
    assert _methods(post) == ["reactions.add"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["already_reacted", "no_reaction"])
async def test_a_reaction_that_is_already_in_the_wanted_state_is_not_an_error(error: str) -> None:
    ch = _make_channel()
    with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_error(error)):
        await ch.react_to_message("C1", "1.1", EYES)
        await ch.react_to_message("C1", "1.1", "")
