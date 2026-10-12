"""The autouse conftest fixture unregisters the auto-mode security reviewer between tests.

The two tests are order dependent on purpose: the second one only passes when the reviewer registered
by the first one was cleared between tests.
"""

from myrm_agent_harness.agent.middlewares.approval import _batch_review
from myrm_agent_harness.agent.middlewares.approval._batch_review import register_security_reviewer
from myrm_agent_harness.agent.security.types import ReviewDecision, ReviewResult


class _AllowReviewer:
    async def review(self, command: str, **kwargs: object) -> ReviewResult:
        return ReviewResult(decision=ReviewDecision.ALLOW, reason="test")


def test_registration_is_visible_inside_the_registering_test() -> None:
    reviewer = _AllowReviewer()

    register_security_reviewer(reviewer)

    assert _batch_review._security_reviewer is reviewer


def test_reviewer_from_the_previous_test_is_gone() -> None:
    assert _batch_review._security_reviewer is None
