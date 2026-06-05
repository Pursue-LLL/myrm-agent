from datetime import datetime

import pytest

from app.database.dto import MessageDTO, _TitleModelConfig
from app.services.chat.chat_turn import _ChatTurnMixin


@pytest.mark.asyncio
async def test_generate_chat_title_empty_messages():
    """Test fallback when no messages are provided."""
    title = await _ChatTurnMixin.generate_chat_title(messages=[])
    assert title == "Untitled Chat"


@pytest.mark.asyncio
async def test_generate_chat_title_no_user_messages():
    """Test fallback when no user messages are provided."""
    msg = MessageDTO(
        id="1",
        chat_id="c1",
        role="assistant",
        content="Hello",
        sent_at=datetime.now(),
        sent_timezone="UTC",
        created_at=datetime.now(),
    )
    title = await _ChatTurnMixin.generate_chat_title(messages=[msg])
    assert title == "Untitled Chat"


@pytest.mark.asyncio
async def test_generate_chat_title_code_snippet_fallback():
    """Test fallback when input is just a code block."""
    msg = MessageDTO(
        id="1",
        chat_id="c1",
        role="user",
        content="```python\nprint('hello')\n```",
        sent_at=datetime.now(),
        sent_timezone="UTC",
        created_at=datetime.now(),
    )
    title = await _ChatTurnMixin.generate_chat_title(messages=[msg])
    assert title == "Python Snippet"


@pytest.mark.asyncio
async def test_generate_chat_title_untagged_code_snippet_fallback():
    """Test fallback when input is an untagged code block."""
    msg = MessageDTO(
        id="1",
        chat_id="c1",
        role="user",
        content="```\nprint('hello')\n```",
        sent_at=datetime.now(),
        sent_timezone="UTC",
        created_at=datetime.now(),
    )
    title = await _ChatTurnMixin.generate_chat_title(messages=[msg])
    assert title == "Snippet"


def test_generate_fallback_title_short():
    """Test the static fallback generator with short text."""
    title = _ChatTurnMixin._generate_fallback_title("Hi")
    assert title == "Untitled Chat"


def test_generate_fallback_title_long():
    """Test the static fallback generator with long text."""
    title = _ChatTurnMixin._generate_fallback_title("This is a very long message that should be truncated.")
    assert title == "This is a very long ..."


@pytest.mark.asyncio
async def test_generate_chat_title_no_model():
    """Test fallback when title_model is None."""
    msg = MessageDTO(
        id="1",
        chat_id="c1",
        role="user",
        content="Hello world",
        sent_at=datetime.now(),
        sent_timezone="UTC",
        created_at=datetime.now(),
    )
    title = await _ChatTurnMixin.generate_chat_title(messages=[msg], title_model=None)
    assert title == "Hello world"


@pytest.mark.asyncio
async def test_generate_chat_title_llm_exception(monkeypatch):
    """Test fallback when LLM call throws an exception."""
    msg = MessageDTO(
        id="1",
        chat_id="c1",
        role="user",
        content="Hello world exception",
        sent_at=datetime.now(),
        sent_timezone="UTC",
        created_at=datetime.now(),
    )

    # Mock _call_llm_for_title to raise an exception
    async def mock_call(*args, **kwargs):
        raise ValueError("Simulated LLM failure")

    monkeypatch.setattr(_ChatTurnMixin, "_call_llm_for_title", mock_call)

    title_model_config = _TitleModelConfig(model="test-model", apiKey="test-key", baseUrl="http://test")

    title = await _ChatTurnMixin.generate_chat_title(messages=[msg], title_model=title_model_config)
    assert title == "Hello world exceptio..."
