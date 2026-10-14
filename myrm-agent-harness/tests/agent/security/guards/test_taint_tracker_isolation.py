"""The autouse conftest fixture resets the context-local taint tracker between tests.

The two tests are order dependent on purpose: the second one only passes when the label recorded by
the first one was cleared between tests.
"""

from myrm_agent_harness.agent.security.guards.taint_tracker import TaintLabel, get_taint_tracker


def test_recorded_label_is_visible_inside_the_recording_test() -> None:
    get_taint_tracker().record(TaintLabel.EXTERNAL_NETWORK, "https://example.invalid/page")

    assert get_taint_tracker().is_tainted


def test_label_from_the_previous_test_is_gone() -> None:
    assert not get_taint_tracker().is_tainted
