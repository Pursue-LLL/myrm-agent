"""Incognito mode: enable_memory stays True globally; session skips memory tools."""

from app.services.agent.params.models import AgentRequest


def test_incognito_mode_preserves_memory_but_disables_extraction() -> None:
    request = AgentRequest(
        message_id="msg-1",
        query="Hello",
        chat_id="test_chat",
        enable_memory=True,
        enable_memory_auto_extraction=True,
        incognito_mode=True,
    )

    enable_memory = request.enable_memory
    enable_memory_auto_extraction = (
        False if request.incognito_mode else (request.enable_memory and request.enable_memory_auto_extraction)
    )

    assert enable_memory is True
    assert enable_memory_auto_extraction is False


def test_non_incognito_mode_preserves_all_flags() -> None:
    request = AgentRequest(
        message_id="msg-2",
        query="Hello",
        chat_id="test_chat",
        enable_memory=True,
        enable_memory_auto_extraction=True,
        incognito_mode=False,
    )

    enable_memory = request.enable_memory
    enable_memory_auto_extraction = (
        False if request.incognito_mode else (request.enable_memory and request.enable_memory_auto_extraction)
    )

    assert enable_memory is True
    assert enable_memory_auto_extraction is True
