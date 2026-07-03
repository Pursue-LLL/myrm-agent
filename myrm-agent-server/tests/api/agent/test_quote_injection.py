"""划词引用注入集成测试

验证 quote 字段从 API 请求到 Agent 上下文的完整链路：
- API 接收 quote 字段
- Agent 将引用内容注入到 LLM 上下文
- LLM 能感知引用内容并在回复中体现
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _collect_agent_response(
    client: TestClient,
    query: str,
    quote: str | None = None,
) -> tuple[str, list[dict[str, object]]]:
    """发送 agent 请求并收集完整响应"""
    request_body: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }
    if quote is not None:
        request_body["quote"] = quote

    events: list[dict[str, object]] = []
    chunks: list[str] = []

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as resp:
        if resp.status_code != 200:
            resp.read()
            pytest.fail(f"HTTP {resp.status_code}: {resp.text}")
        for line in resp.iter_lines():
            line = line.strip()
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                events.append(data)
                if data.get("type") == "message" and data.get("data"):
                    chunks.append(str(data["data"]))
            except json.JSONDecodeError:
                pass

    check_e2e_errors(events)
    return "".join(chunks), events


@pytest.mark.skipif(
    not os.getenv("BASIC_API_KEY"),
    reason="BASIC_API_KEY not set",
)
class TestQuoteInjection:
    """划词引用 E2E 集成测试"""

    def test_quote_field_accepted(self, client: TestClient) -> None:
        """API 接受 quote 字段且不报错"""
        answer, events = _collect_agent_response(
            client,
            query="简单回复一个字：好",
            quote="这是一段被引用的测试文本",
        )
        assert len(events) > 0, "应该收到至少一个事件"
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 0, f"不应有错误事件: {error_events}"

    def test_quote_content_perceived_by_llm(self, client: TestClient) -> None:
        """LLM 能感知引用内容并在回复中体现"""
        magic_word = "Zypherion42"
        answer, events = _collect_agent_response(
            client,
            query="请告诉我，在引用的上下文中出现了什么特殊单词？只回复那个单词即可。",
            quote=f"这段文字中包含一个特殊单词：{magic_word}，请记住它。",
        )
        if not answer:
            pytest.skip("LLM returned empty response (model may be rate-limited or unavailable)")
        assert magic_word in answer, f"LLM 应该在回复中包含引用中的特殊单词 '{magic_word}'，但实际回复: {answer[:200]}"

    def test_no_quote_still_works(self, client: TestClient) -> None:
        """不带 quote 时正常工作（回归测试）"""
        answer, events = _collect_agent_response(
            client,
            query="回复数字1",
        )
        assert len(events) > 0
        assert "1" in answer
