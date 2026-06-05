import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.sub_agents.types import SubAgentResult

from app.services.agent.wakeup_handler import ServerWakeupHandler
from app.services.chat.chat_service import ChatService
from app.services.event.app_event_bus import AppEventType, get_event_bus


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_server_wakeup_handler_e2e(client: TestClient) -> None:
    """测试 ServerWakeupHandler 在真实场景下的端到端执行。

    验证：
    1. 数据库写入系统通知。
    2. 触发 Headless Agent 运行。
    3. EventBus 发布 ASYNC_AGENT_STREAM_CHUNK 事件。
    """
    # 1. 创建一个真实的 Chat Session
    session_id = str(uuid.uuid4())

    # 初始化 Chat
    from datetime import datetime, timezone

    await ChatService.ensure_chat_and_append_user_message(
        chat_id=session_id,
        content="Test Wakeup Session",
        sent_at=datetime.now(tz=timezone.utc),
        sent_timezone="UTC",
        message_id=str(uuid.uuid4()),
        action_mode="general",
    )

    # 2. 构造一个 SubAgentResult
    result = SubAgentResult(
        task_id="task-e2e-001",
        agent_type="test_crawler",
        success=True,
        result="Found some interesting facts about Python 3.14. Please directly output these facts to the user without calling any tools.",
        duration_seconds=1.5,
    )

    # 3. 订阅 EventBus
    bus = get_event_bus()
    queue = bus.subscribe()

    # 4. 触发唤醒
    handler = ServerWakeupHandler()
    await handler.on_async_wakeup(result, "general", session_id)

    # 5. 等待并收集事件
    collected_chunks = []
    has_message_end = False

    try:
        # 等待最多 60 秒
        async with asyncio.timeout(60.0):
            while not has_message_end:
                event = await queue.get()
                if event.event_type == AppEventType.ASYNC_AGENT_STREAM_CHUNK:
                    data = event.data
                    if data.get("session_id") == session_id:
                        chunk = data.get("chunk", {})
                        chunk_type = chunk.get("type")
                        collected_chunks.append(chunk)
                        if chunk_type == "message_end":
                            has_message_end = True
                        elif chunk_type == "error":
                            pytest.fail(f"Agent stream returned error: {chunk.get('error')}")
    except asyncio.TimeoutError:
        pytest.fail("Timeout waiting for ASYNC_AGENT_STREAM_CHUNK message_end event")
    finally:
        bus.unsubscribe(queue)

    # 6. 验证结果
    assert has_message_end, "Should have received message_end event"
    assert len(collected_chunks) > 0, "Should have received stream chunks"

    # 7. 验证数据库中是否写入了系统通知和回复
    # 等待后台 consume_stream 任务完成 finally 块中的数据库写入
    for _ in range(10):
        history = await ChatService.load_web_chat_history(session_id, api_key=None)
        if len(history) >= 3:
            break
        await asyncio.sleep(0.5)

    # 应该至少有一条初始化消息，一条 system_notification 和一条 assistant 的回复
    assert len(history) >= 3

    system_msg = next((msg for msg in history if msg[0] == "human" and "async_result" in msg[1]), None)
    assert system_msg is not None, "Should have found system_notification"
    assert "task-e2e-001" in system_msg[1]

    assistant_msg = history[-1]
    assert assistant_msg[0] == "assistant"
    assert len(assistant_msg[1]) > 0
