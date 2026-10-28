"""A whole turn's status reactions on a platform that removes reactions by name (Slack).

``_cleanup_effects`` (end of every turn, ``/stop``, stuck-task janitor, TTL) and the completion
reaction both clear the processing reaction with an empty emoji. The first clear must remove it
from the message, and the second must not call the platform again.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.message_effects import MessageEffects
from tests.channels.providers.slack.test_slack_channel import _make_channel, _ok_json

EYES = "\U0001f440"
CHECK = "\u2705"
CROSS = "\u274c"


@pytest.fixture
def slack_effects() -> Iterator[tuple[MessageEffects, AsyncMock]]:
    slack = _make_channel()
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=slack)
    with patch.object(slack._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as post:
        yield MessageEffects(bus), post


def _calls(post: AsyncMock) -> list[tuple[str, str]]:
    return [(c.args[0].rsplit("/", 1)[-1], c.kwargs["json"]["name"]) for c in post.await_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize(("success", "final"), [(True, "white_check_mark"), (False, "x")])
async def test_a_finished_turn_swaps_the_processing_reaction_for_the_result(
    slack_effects: tuple[MessageEffects, AsyncMock], success: bool, final: str
) -> None:
    fx, post = slack_effects

    await fx.ack_reaction("slack", "C1", "1.1", EYES)
    await fx.set_reaction("slack", "C1", "1.1", "")
    await fx.completion_reaction("slack", "C1", "1.1", success=success, success_emoji=CHECK, failure_emoji=CROSS, had_ack=True)

    assert _calls(post) == [("reactions.add", "eyes"), ("reactions.remove", "eyes"), ("reactions.add", final)]


@pytest.mark.asyncio
async def test_a_stopped_turn_leaves_no_processing_reaction_behind(slack_effects: tuple[MessageEffects, AsyncMock]) -> None:
    fx, post = slack_effects

    await fx.ack_reaction("slack", "C1", "1.1", EYES)
    await fx.set_reaction("slack", "C1", "1.1", "")

    assert _calls(post) == [("reactions.add", "eyes"), ("reactions.remove", "eyes")]
