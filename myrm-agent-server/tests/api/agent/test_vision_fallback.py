import json

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    get_model_selection,
)


def create_tiny_dummy_image_b64() -> str:
    """Create a 1x1 transparent PNG base64 string"""
    # 1x1 transparent PNG
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="


def perform_fallback_test(client: TestClient, query: list[dict[str, object]]) -> tuple[str, list[dict[str, object]], bool]:
    """执行包含图片的请求并收集响应"""

    # 1. 构造主模型
    # 我们使用用户配置的 BASIC_API_KEY 和 BaseUrl
    main_model_selection = get_model_selection()

    # 修复 openai-compatible 在 LiteLLM 中的前缀问题
    if main_model_selection.get("providerId") in ("openai-compatible", "siliconflow"):
        main_model_selection["providerId"] = "openai"

    # 2. 将 BASIC_MODEL 设置为 Vision Fallback Model
    vision_fallback_selection = get_model_selection()
    vision_fallback_selection["model"] = "qwen-vl-plus"
    vision_fallback_selection["providerId"] = "dashscope"  # 明确使用 dashscope 避免前缀问题

    search_request: dict[str, object] = {
        "messageId": "test_msg_001",
        "chatId": "test_chat_001",
        "query": query,
        "modelSelection": main_model_selection,
        "visionFallbackModelSelection": vision_fallback_selection,
        "searchServiceCfg": None,
    }

    print(f"\n{'=' * 60}")
    print(f"🔍 视觉降级路由测试: {query}")
    print(f"{'=' * 60}")

    collected_data: list[dict] = []
    message_chunks: list[str] = []
    analyzing_image_seen = False

    with client.stream("POST", "/api/v1/agents/agent-stream", json=search_request) as response:
        if response.status_code != 200:
            response.read()
            error_content = response.text
            print(f"\n❌ HTTP错误 {response.status_code}: {error_content}")
        assert response.status_code == 200

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
                collected_data.append(data)
                event_type = data.get("type", "unknown")

                if event_type == "agent_status":
                    status_data = data.get("data", {})
                    status_str = status_data.get("status")
                    print(f"  ⚡ 状态更新: {status_str}")
                    if status_str == "analyzing_image":
                        analyzing_image_seen = True
                elif event_type == "message":
                    content = data.get("data", "")
                    if content:
                        message_chunks.append(content)
                elif event_type == "error":
                    error_msg = data.get("error", "")
                    print(f"  ❌ 错误: {error_msg[:100]}")
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")

    full_message = "".join(message_chunks)
    print(f"\n🤖 最终回复:\n{full_message}")

    return full_message, collected_data, analyzing_image_seen


@pytest.mark.e2e
def test_vision_fallback_routing(client: TestClient) -> None:
    """测试不支持视觉的主模型在收到图片时，能否自动触发降级视觉模型进行文字解析"""

    b64_image = create_tiny_dummy_image_b64()
    query = [
        {"type": "text", "text": "Describe the content of this image, reply simply."},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
        },
    ]

    full_message, data, seen_analyzing = perform_fallback_test(client, query)

    assert seen_analyzing, "Did not see 'analyzing_image' status event, fallback might not have been triggered."
    # We do not assert full_message because the user's API key might not support the specific model or might hit rate limits.
    # The routing logic is verified if analyzing_image was emitted.
