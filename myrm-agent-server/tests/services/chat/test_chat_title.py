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


@pytest.mark.asyncio
async def test_call_llm_for_title_keeps_its_cap_off_the_thinking_floor(monkeypatch):
    """A title keeps its own small cap: the call opts out of the thinking-model output floor."""
    from langchain_core.messages import AIMessage
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.services.chat.chat_title import call_llm_for_title

    captured = {}

    class _TitleLlm:
        async def ainvoke(self, _messages):
            return AIMessage(content="Asyncio blocking")

    async def _get_llm_from_config(cfg, *, streaming):
        captured["cfg"] = cfg
        return _TitleLlm()

    monkeypatch.setattr(llm_manager, "get_llm_from_config", _get_llm_from_config)

    title = await call_llm_for_title(
        "Why does asyncio block?",
        _TitleModelConfig(model="o3-mini", apiKey="test-key", baseUrl="http://test"),
    )

    assert title == "Asyncio blocking"
    assert captured["cfg"].model_kwargs["max_tokens"] == 1024
    assert captured["cfg"].model_kwargs["supports_reasoning"] is False
