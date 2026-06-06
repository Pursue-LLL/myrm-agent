from datetime import datetime

import pytest

from app.database.dto import MessageDTO
from app.services.chat.chat_turn import _ChatTurnMixin


@pytest.mark.asyncio
async def test_truncation_unclosed_code_block():
    # Simulate a massive code block that gets truncated
    massive_code = "```python\n" + ("print('hello')\n" * 500)
    msg = MessageDTO(
        id="1", chat_id="c1", role="user", content=massive_code,
        sent_at=datetime.now(), sent_timezone="UTC", created_at=datetime.now()
    )
    
    # We don't pass title_model, so it falls back to _generate_fallback_title
    # If the code block is NOT stripped, the fallback title will be "```python\nprint('he..."
    # If it IS stripped, it should return "Python Snippet"
    
    title = await _ChatTurnMixin.generate_chat_title(messages=[msg], title_model=None)
    print(f"Generated title: {title}")
    assert title == "Python Snippet"

