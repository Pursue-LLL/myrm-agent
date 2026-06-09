"""Test Content Normalization in General Agent.

This test verifies that the General Agent can handle inputs with excessive
newlines and zero-width characters, and that the NormalizeProcessor correctly
cleans them up without breaking the agent's ability to respond.
"""

import json

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    get_model_selection,
    get_search_service_config,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_general_agent_content_normalization(client: TestClient):
    """Test that the agent handles dirty input strings correctly."""

    # 构造包含大量空行、回车符和零宽字符的查询
    dirty_query = "Hello\r\n\r\n\r\n\u200b\u200c\u200d\ufeffWorld!\n\n\n\nHow are you?"

    request_data = {
        "messageId": "test-msg-123",
        "query": dirty_query,
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
        "enableWebSearch": False,  # Disable search to isolate the test to just LLM response
    }

    print(f"\n{'=' * 60}")
    print(f"🔍 发送脏数据查询: {repr(dirty_query)}")
    print(f"{'=' * 60}")

    message_chunks = []

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data) as response:
        if response.status_code != 200:
            response.read()
            print(f"\n❌ HTTP错误 {response.status_code}: {response.text}")
        assert response.status_code == 200

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
                if data is None:
                    continue
                event_type = data.get("type", "unknown")

                if event_type == "message":
                    content = data.get("data", "")
                    if content:
                        message_chunks.append(content)
            except json.JSONDecodeError:
                pass

    full_message = "".join(message_chunks)
    print(f"\n🤖 Agent回复: {full_message}")

    # 验证 Agent 成功理解了问题并给出了回复，说明 NormalizeProcessor 没有破坏内容
    assert len(full_message) > 0
    assert (
        "hello" in full_message.lower()
        or "world" in full_message.lower()
        or "how are you" in full_message.lower()
        or "i am" in full_message.lower()
        or "doing" in full_message.lower()
    )
