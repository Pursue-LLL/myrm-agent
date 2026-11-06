"""AgentRequest wire contract: a turn is always answered on the POST response body."""

from app.services.agent.params.models import AgentRequest


def test_the_request_has_no_turn_transport_switch() -> None:
    assert "multiplexed" not in AgentRequest.model_fields


def test_a_client_that_still_sends_the_retired_flag_is_accepted_and_nothing_changes() -> None:
    plain = AgentRequest.model_validate({"message_id": "m1", "query": "hi"})
    legacy = AgentRequest.model_validate({"message_id": "m1", "query": "hi", "multiplexed": True})

    assert legacy.model_dump() == plain.model_dump()


def test_a_turn_carries_the_folder_the_viewer_picked_before_the_chat_existed() -> None:
    snake = AgentRequest.model_validate({"message_id": "m1", "query": "hi", "workspace_dir": "/work/reports"})
    camel = AgentRequest.model_validate({"messageId": "m1", "query": "hi", "workspaceDir": "/work/reports"})

    assert snake.workspace_dir == "/work/reports"
    assert camel.workspace_dir == "/work/reports"
    assert AgentRequest.model_validate({"message_id": "m1"}).workspace_dir is None


def test_a_blank_folder_is_no_folder() -> None:
    blank = AgentRequest.model_validate({"message_id": "m1", "workspace_dir": "   "})
    padded = AgentRequest.model_validate({"message_id": "m1", "workspace_dir": "  /work/reports\n"})

    assert blank.workspace_dir is None
    assert padded.workspace_dir == "/work/reports"
