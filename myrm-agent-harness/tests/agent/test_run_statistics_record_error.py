"""AgentRunStatistics keeps a run's failure as text with credentials masked."""

from myrm_agent_harness.agent.types import AgentRunStatistics

_ECHOED_KEY = "sk-" + "a1b2c3d4" * 5


def test_the_failure_reads_as_the_error_type_and_its_message() -> None:
    stats = AgentRunStatistics()

    stats.record_error("RuntimeError", "unrecoverable error")

    assert stats.error_message == "RuntimeError: unrecoverable error"


def test_a_key_the_provider_echoed_back_is_masked_and_the_rest_of_the_message_stays() -> None:
    stats = AgentRunStatistics()

    stats.record_error("AuthenticationError", f"Incorrect API key provided: {_ECHOED_KEY}. Check your account.")

    assert stats.error_message is not None
    assert _ECHOED_KEY not in stats.error_message
    assert stats.error_message.startswith("AuthenticationError: Incorrect API key provided: ")
    assert stats.error_message.endswith(". Check your account.")
