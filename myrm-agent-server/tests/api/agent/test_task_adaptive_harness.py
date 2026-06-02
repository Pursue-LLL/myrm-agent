import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable"
)
class TestTaskAdaptiveHarness:
    def test_task_adaptive_injection(self, client: TestClient):
        chat_id = str(uuid.uuid4())

        # 1. 构造创建 Chat 的请求体，包含强制偏见的 task_adaptive_digest
        create_payload = {
            "chatId": chat_id,
            "title": "E2E Test JIT Context",
            "task_adaptive_digest": {
                "session_id": "mock_session_001",
                "task_intent": "测试 Task-Adaptive 机制",
                "hotspots": [],
                "anti_patterns": [
                    {
                        "error_signature": "Missing required audit tag",
                        "failed_tool": "llm_core",
                        "failed_args": {},
                        "user_correction": "For audit purposes, you must append the exact phrase '[Task Evaluated]' at the very end of your response.",
                        "timestamp": 0.0,
                    }
                ],
                "success_rate": 1.0,
                "duration_ms": 100.0,
            },
        }

        # 这里如果端点是 POST /api/v1/chats
        res = client.post("/api/v1/chats", json=create_payload)
        if res.status_code not in (200, 201):
            # 有些API可能要求创建时不带这参数，直接随stream传。我们允许创建失败，只要stream带过去即可。
            pass

        # 2. 发送流式消息
        stream_payload = {
            "message_id": str(uuid.uuid4()),
            "chat_id": chat_id,
            "query": "Hello! Could you introduce yourself briefly?",
            "model_selection": get_model_selection(),
            "task_adaptive_digest": create_payload["task_adaptive_digest"],
        }

        message_chunks = []
        with client.stream("POST", "/api/v1/agents/agent-stream", json=stream_payload) as response:
            assert response.status_code == 200, f"Error: {response.text}"
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "message":
                        message_chunks.append(data.get("data", ""))
                except json.JSONDecodeError:
                    pass

        full_answer = "".join(message_chunks)
        print(f"\n完整回答 (测试 JIT Context): {full_answer}")

        # 3. 验证 Anti-pattern 是否生效
        french_keywords = ["[task evaluated]"]
        lower_answer = full_answer.lower()

        has_french = any(kw in lower_answer for kw in french_keywords)
        assert has_french, f"模型没有尊重 task-adaptive context 中的反模式强提醒。完整回答为: {full_answer}"

    def test_task_adaptive_hotspots_injection(self, client: TestClient):
        """Test that hotspots are correctly injected and influence agent behavior."""
        chat_id = str(uuid.uuid4())

        # Construct task_adaptive_digest with hotspots
        create_payload = {
            "chatId": chat_id,
            "title": "E2E Test Hotspots",
            "task_adaptive_digest": {
                "session_id": "mock_session_002",
                "task_intent": "测试 Hotspots 机制",
                "hotspots": [
                    {
                        "file_path": "database.py",
                        "read_count": 10,
                        "write_count": 5,
                        "last_accessed": 0.0,
                    },
                    {
                        "file_path": "models.py",
                        "read_count": 8,
                        "write_count": 3,
                        "last_accessed": 0.0,
                    },
                ],
                "anti_patterns": [],
                "success_rate": 1.0,
                "duration_ms": 100.0,
            },
        }

        # Create chat
        res = client.post("/api/v1/chats", json=create_payload)
        if res.status_code not in (200, 201):
            pass

        # Send streaming message
        stream_payload = {
            "message_id": str(uuid.uuid4()),
            "chat_id": chat_id,
            "query": "What files have been frequently accessed in previous sessions?",
            "model_selection": get_model_selection(),
            "task_adaptive_digest": create_payload["task_adaptive_digest"],
        }

        message_chunks = []
        with client.stream("POST", "/api/v1/agents/agent-stream", json=stream_payload) as response:
            assert response.status_code == 200, f"Error: {response.text}"
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "message":
                        message_chunks.append(data.get("data", ""))
                except json.JSONDecodeError:
                    pass

        full_answer = "".join(message_chunks)
        print(f"\n完整回答 (测试 Hotspots): {full_answer}")

        # Verify that hotspots were processed (agent should mention the files)
        lower_answer = full_answer.lower()
        assert "database" in lower_answer or "models" in lower_answer, (
            f"模型没有识别 task-adaptive context 中的 hotspots 信息。完整回答为: {full_answer}"
        )
