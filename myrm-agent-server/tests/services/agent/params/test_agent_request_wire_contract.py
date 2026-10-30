"""AgentRequest wire contract: a turn is always answered on the POST response body."""

from app.services.agent.params.models import AgentRequest


def test_the_request_has_no_turn_transport_switch() -> None:
    assert "multiplexed" not in AgentRequest.model_fields


def test_a_client_that_still_sends_the_retired_flag_is_accepted_and_nothing_changes() -> None:
    plain = AgentRequest.model_validate({"message_id": "m1", "query": "hi"})
    legacy = AgentRequest.model_validate({"message_id": "m1", "query": "hi", "multiplexed": True})

    assert legacy.model_dump() == plain.model_dump()
