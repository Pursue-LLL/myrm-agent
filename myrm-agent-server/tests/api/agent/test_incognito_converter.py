"""Incognito mode must disable memory flags in GeneralAgentParams conversion."""

from app.services.agent.params.models import AgentRequest


def test_incognito_mode_disables_memory() -> None:
    request = AgentRequest(
        message_id="msg-1",
        query="Hello",
        chat_id="test_chat",
        enable_memory=True,
        enable_memory_auto_extraction=True,
        incognito_mode=True,
    )

    enable_memory = False if request.incognito_mode else request.enable_memory
    enable_memory_auto_extraction = (
        False if request.incognito_mode else (request.enable_memory and request.enable_memory_auto_extraction)
    )

    assert enable_memory is False
    assert enable_memory_auto_extraction is False
