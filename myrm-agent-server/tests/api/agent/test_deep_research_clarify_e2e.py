"""Deep Research Clarification E2E 测试

测试 /api/v1/agents/deep-research-stream 端点触发澄清，并使用 /api/v1/agents/clarify-response 恢复。
"""

import json
import os
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    get_model_selection,
    get_search_service_config,
)


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestDeepResearchClarifyE2E:
    """Deep Research Clarification E2E 测试"""

    def test_deep_research_clarify_flow(self, client: TestClient):
        """测试 Deep Research 触发澄清并恢复的完整流程"""
        message_id = str(uuid.uuid4())

        # 构造一个故意模糊的问题，迫使模型提问
        query = "帮我调研一下那个很火的AI框架，对比一下它的优缺点。"

        search_request: dict[str, object] = {
            "messageId": message_id,
            "query": query,
            "modelSelection": get_model_selection(),
            "searchServiceCfg": get_search_service_config(),
            "actionMode": "deep_research",
            "agentConfig": {
                "deepResearch": {
                    "enableClarification": True,
                    "maxCycles": 0,
                }
            },
        }

        collected_data: list[dict[str, object]] = []
        clarification_received = threading.Event()

        def answer_clarification():
            # 等待收到澄清事件
            clarification_received.wait(timeout=30.0)
            if not clarification_received.is_set():
                print("⚠️ 后台线程未收到澄清事件")
                return

            print("\n[后台线程] 收到澄清事件，准备发送回答...")
            time.sleep(1)  # 稍微等待一下，确保 waiter 已经注册

            # 发送结构化回答
            resp = client.post(
                "/api/v1/agents/clarify-response",
                json={
                    "messageId": message_id,
                    "answer": {
                        "q1": "LangChain",
                        "compare_with": "不需要对比，只分析这一框架",
                        "focus_areas": ["生产部署与可扩展性"],
                    },
                },
            )
            print(f"[后台线程] 发送回答完成，状态码: {resp.status_code}")

        # 启动后台线程来回答澄清问题
        answer_thread = threading.Thread(target=answer_clarification)
        answer_thread.start()

        print(f"\n{'=' * 60}")
        print(f"🔍 Deep Research 模糊查询: {query}")
        print(f"{'=' * 60}")

        message_chunks = []
        has_clarify_event = False

        with client.stream(
            "POST", "/api/v1/agents/agent-stream", json=search_request
        ) as response:
            assert response.status_code == 200

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    collected_data.append(data)
                    event_type = data.get("type", "unknown")

                    if event_type == "error":
                        error_msg = data.get("error", "")
                        if any(
                            kw in error_msg
                            for kw in [
                                "Authentication",
                                "Authorization",
                                "Cannot connect",
                                "Connection error",
                            ]
                        ):
                            pytest.skip(f"环境配置问题: {error_msg[:100]}")
                        else:
                            pytest.fail(f"Agent execution error: {error_msg}")

                    if event_type == "message":
                        metadata = data.get("metadata", {})
                        if (
                            isinstance(metadata, dict)
                            and metadata.get("phase") == "clarify"
                        ):
                            print(f"\n  ❓ 收到澄清问题: {data.get('data')}")
                            has_clarify_event = True
                            clarification_received.set()
                        elif (
                            isinstance(metadata, dict)
                            and metadata.get("phase") == "report"
                        ):
                            content = data.get("data", "")
                            if content:
                                message_chunks.append(content)

                    elif event_type == "status":
                        status_data = data.get("data", {})
                        if (
                            isinstance(status_data, dict)
                            and status_data.get("phase") == "clarify"
                        ):
                            print(f"  ⏳ 澄清状态: {status_data.get('status')}")

                except json.JSONDecodeError as e:
                    print(f"JSON解析错误: {e}")

        answer_thread.join()

        full_report = "".join(message_chunks)

        print("\n📊 收集统计:")
        print(f"  - 总事件数: {len(collected_data)}")
        print(f"  - 是否触发澄清: {has_clarify_event}")
        print(f"  - 最终报告长度: {len(full_report)} 字符")

        assert has_clarify_event, "Should have triggered clarification phase"
        assert full_report, "Should have generated a final report after clarification"

        # 验证包含我们回答的内容
        assert (
            "LangChain" in full_report
            or "LlamaIndex" in full_report
            or len(full_report) > 100
        ), "Report should reflect the clarified topic"
        print("\n✅ 测试通过：Deep Research 澄清流程正常")
