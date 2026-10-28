"""A whole turn's status reactions on a platform that removes reactions by name (Slack).

The turn's status reaction takes the processing reaction off with an empty emoji; the platform is asked to
remove exactly the reaction that was added, and a turn that never added one asks nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.reactions import StatusReaction, TurnOutcome
from app.channels.routing.router_models import ReactionPolicy
from tests.channels.providers.slack.test_slack_channel import _make_channel, _ok_json


@pytest.fixture
def slack_status() -> Iterator[tuple[StatusReaction, AsyncMock]]:
    slack = _make_channel()
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=slack)
    with patch.object(slack._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as post:
        yield StatusReaction(MessageEffects(bus), ReactionPolicy(), "slack", "C1", "1.1"), post


def _calls(post: AsyncMock) -> list[tuple[str, str]]:
    return [(c.args[0].rsplit("/", 1)[-1], c.kwargs["json"]["name"]) for c in post.await_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize(("outcome", "final"), [(TurnOutcome.COMPLETED, "white_check_mark"), (TurnOutcome.FAILED, "x")])
async def test_a_finished_turn_swaps_the_processing_reaction_for_the_result(
    slack_status: tuple[StatusReaction, AsyncMock], outcome: TurnOutcome, final: str
) -> None:
    status, post = slack_status

    await status.received()
    await status.finish(outcome)

    assert _calls(post) == [("reactions.add", "eyes"), ("reactions.remove", "eyes"), ("reactions.add", final)]


@pytest.mark.asyncio
async def test_a_stopped_turn_leaves_no_processing_reaction_behind(slack_status: tuple[StatusReaction, AsyncMock]) -> None:
    status, post = slack_status

    await status.received()
    await status.finish(TurnOutcome.ABANDONED)

    assert _calls(post) == [("reactions.add", "eyes"), ("reactions.remove", "eyes")]
