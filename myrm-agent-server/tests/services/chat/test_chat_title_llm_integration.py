import os
import time
from datetime import datetime

import pytest

from app.database.dto import MessageDTO, _TitleModelConfig
from app.services.chat.chat_turn import _ChatTurnMixin
from tests.support.test_secrets import resolve_test_env


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_generate_chat_title_integration():
    """测试真实的 LLM 标题生成逻辑"""
    model = resolve_test_env("BASIC_MODEL") or "gpt-4o-mini"
    api_key = resolve_test_env("BASIC_API_KEY")
    base_url = resolve_test_env("BASIC_BASE_URL")

    title_model_config = _TitleModelConfig(model=model, apiKey=api_key, baseUrl=base_url)

    msg1 = MessageDTO(
        id="1",
        chat_id="c1",
        role="user",
        content="Can you explain how the event loop works in Python asyncio? I am getting some blocking issues.",
        sent_at=datetime.now(),
        sent_timezone="UTC",
        created_at=datetime.now(),
    )
    msg2 = MessageDTO(
        id="2",
        chat_id="c1",
        role="assistant",
        content="The event loop is the core of every asyncio application. It runs asynchronous tasks and callbacks...",
        sent_at=datetime.now(),
        sent_timezone="UTC",
        created_at=datetime.now(),
    )

    title = await _ChatTurnMixin.generate_chat_title(messages=[msg1, msg2], title_model=title_model_config)

    assert isinstance(title, str)
    assert len(title) > 0
    assert title != "Untitled Chat"
    assert title != "Snippet"
    print(f"\nGenerated Title: {title}")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_generate_chat_title_massive_input_early_truncation():
    """测试 O(1) 早期截断防阻塞逻辑：传入超大文本，验证是否会卡死"""
    model = resolve_test_env("BASIC_MODEL") or "gpt-4o-mini"
    api_key = resolve_test_env("BASIC_API_KEY")
    base_url = resolve_test_env("BASIC_BASE_URL")

    title_model_config = _TitleModelConfig(model=model, apiKey=api_key, baseUrl=base_url)

    # 构造约 1MB 的超大输入
    massive_content = "Here is my massive log file:\n" + ("error line 500 internal server error\n" * 50000)

    msg1 = MessageDTO(
        id="1",
        chat_id="c1",
        role="user",
        content=massive_content,
        sent_at=datetime.now(),
        sent_timezone="UTC",
        created_at=datetime.now(),
    )

    start_time = time.time()
    title = await _ChatTurnMixin.generate_chat_title(messages=[msg1], title_model=title_model_config)
    end_time = time.time()

    assert isinstance(title, str)
    assert len(title) > 0

    # 如果没有早期截断，1MB 的正则匹配会耗时非常久。
    # 加上网络请求时间，总时间应该在合理范围内（通常 < 5秒，但网络波动可能导致十几秒）。
    elapsed = end_time - start_time
    print(f"\nMassive Input Generated Title: {title} (Took {elapsed:.2f}s)")
    assert elapsed < 30.0, f"Title generation took too long: {elapsed}s, possible CPU blocking or severe network lag."
