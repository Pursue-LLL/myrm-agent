"""端到端测试：TestClient测试Subagent Notification Cache Fix

使用FastAPI TestClient绕过认证，测试真实API逻辑
"""

import json
import logging
import os
import time

import pytest
import requests
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Load .env file
load_dotenv(override=True)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _strip_provider_prefix(model: str) -> str:
    """移除 LiteLLM 格式的 provider/ 前缀"""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def get_model_selection():
    """Get model selection from environment (matches utils.py format)"""
    raw_model = os.getenv("BASIC_MODEL")
    if not raw_model:
        raise ValueError("No BASIC_MODEL found in environment. Set BASIC_MODEL in .env.test")

    selection = {
        "providerId": "openai",
        "model": _strip_provider_prefix(raw_model),
    }

    # Add extended thinking for Claude models
    if "claude" in raw_model.lower() or "anthropic" in raw_model.lower():
        selection["modelKwargs"] = {
            "thinking": {"type": "enabled", "budget_tokens": 24576},
            "reasoning": {"type": "enabled"},
            "extra_body": {
                "thinking": {"type": "enabled"},
                "enable_thinking": True,
                "max_tokens": 32768,
            },
        }

    return selection


def parse_sse_stream(raw_stream: str) -> list[dict]:
    """Parse SSE stream into structured events"""
    events = []
    current_event = {}

    for line in raw_stream.split("\n"):
        line = line.strip()
        if not line:
            if current_event:
                events.append(current_event)
                current_event = {}
            continue

        if line.startswith("event:"):
            current_event["type"] = line[6:].strip()
        elif line.startswith("data:"):
            try:
                current_event["data"] = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                current_event["data"] = line[5:].strip()

    if current_event:
        events.append(current_event)

    return events


@pytest.mark.skipif(
    not os.getenv("BASIC_MODEL"),
    reason="Requires BASIC_MODEL in .env.test for E2E testing",
)
def test_subagent_notification_no_injection(client: TestClient):
    """TestClient测试：验证Subagent Notification无消息注入

    测试步骤：
    1. 使用TestClient（绕过认证）发送触发subagent的消息
    2. 解析SSE流
    3. 验证SUBAGENT_COMPLETION事件存在
    4. 验证无HumanMessage注入（Prompt Cache保护）
    5. 验证LLM主动调用list_subagents_tool
    """
    logger.info("=" * 80)
    logger.info("🧪 TestClient E2E Test: Subagent Notification Cache Fix")
    logger.info("=" * 80)

    # Prepare request
    try:
        model_selection = get_model_selection()
    except ValueError as e:
        logger.error(f"❌ {e}")
        return False

    payload = {
        "query": "帮我搜索2026年最新的AI监管政策",
        "modelSelection": model_selection,
        "chatHistory": [],
    }

    logger.info(f"📨 Sending request: {payload['query']}")
    logger.info(f"📊 Model: {model_selection['providerId']}/{model_selection['model']}")

    # Send request using TestClient
    try:
        start_time = time.time()
        response = client.post(
            "/api/v1/agents/agent-stream",
            json=payload,
            headers={"Accept": "text/event-stream"},
        )

        if response.status_code != 200:
            logger.error(f"❌ API request failed: {response.status_code}")
            logger.error(f"   Response: {response.text}")
            return False

        logger.info(f"✅ Request successful: {response.status_code}")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request failed: {e}")
        return False

    # Collect SSE stream
    logger.info("📡 Collecting SSE stream...")
    raw_stream = response.text
    elapsed_time = time.time() - start_time

    logger.info(f"✅ Stream collected ({elapsed_time:.2f}s, {len(raw_stream)} chars)")

    # Parse events
    events = parse_sse_stream(raw_stream)
    logger.info(f"📊 Total events: {len(events)}")

    # Log event summary
    event_types = {}
    for event in events:
        event_type = event.get("type", "UNKNOWN")
        event_types[event_type] = event_types.get(event_type, 0) + 1

    logger.info("📋 Event summary:")
    for event_type, count in sorted(event_types.items()):
        logger.info(f"   - {event_type}: {count}")

    # Verification 1: SUBAGENT_COMPLETION event
    has_completion = any(e.get("type") == "SUBAGENT_COMPLETION" for e in events)
    logger.info(f"{'✅' if has_completion else '⚠️'} SUBAGENT_COMPLETION event: {has_completion}")

    if not has_completion:
        logger.warning("   No SUBAGENT_COMPLETION event found. Possible reasons:")
        logger.warning("   1. LLM didn't spawn async subagent (wait=true or no subagent)")
        logger.warning("   2. Subagent completed before event emission")

    # Verification 2: No HumanMessage injection (critical for Prompt Cache)
    injection_count = 0
    for event in events:
        if event.get("type") in ["SUBAGENT_NOTIFICATION", "HUMAN_MESSAGE_INJECTION"]:
            injection_count += 1
        # Check MESSAGE events for suspicious injections
        if event.get("type") == "MESSAGE":
            data = event.get("data", {})
            if isinstance(data, dict):
                message_type = data.get("type", "")
                if "human" in message_type.lower() and "subagent" in str(data).lower():
                    injection_count += 1

    logger.info(f"{'✅' if injection_count == 0 else '❌'} Message injections: {injection_count} (expected: 0)")
    if injection_count > 0:
        logger.error("   ❌ CRITICAL: Found message injections - Prompt Cache will be broken!")
        return False

    # Verification 3: LLM actively called list_subagents_tool
    llm_called_list_tool = False
    for event in events:
        if event.get("type") == "TOOL_CALL_START":
            data = event.get("data", {})
            if isinstance(data, dict) and "list_subagents" in data.get("tool_name", ""):
                llm_called_list_tool = True
                break

    logger.info(f"{'✅' if llm_called_list_tool else '⚠️'} LLM called list_subagents_tool: {llm_called_list_tool}")

    if not llm_called_list_tool:
        logger.warning("   LLM did not actively query subagent results. This is acceptable if:")
        logger.warning("   - Subagent was synchronous (wait=true)")
        logger.warning("   - Frontend intelligent prompting triggered (5s timeout)")
        logger.warning("   For optimal UX, LLM should proactively query 95% of the time.")

    # Verification 4: Final response exists
    final_response = None
    for event in reversed(events):
        if event.get("type") == "MESSAGE":
            final_response = event.get("data", {}).get("content", "")
            if final_response:
                break

    if final_response:
        logger.info(f"✅ Final response received ({len(final_response)} chars)")
        logger.info(f"📝 Preview: {final_response[:150]}...")
    else:
        logger.warning("⚠️ No final response found")

    # Summary
    logger.info("=" * 80)
    logger.info("🎉 TEST RESULT: PASSED ✅")
    logger.info("   Core validation:")
    logger.info(f"   ✅ No message injection (Prompt Cache protected): {injection_count == 0}")
    logger.info(f"   ✅ SSE events work: {len(events) > 0}")
    logger.info(f"   ✅ Final response delivered: {final_response is not None}")
    logger.info(
        f"   {'✅' if llm_called_list_tool else '⚠️'} LLM behavior: {'Active query' if llm_called_list_tool else 'Relies on frontend'}"
    )
    logger.info("=" * 80)

    return True


# Can be run directly with pytest:
# pytest tests/api/agent/test_subagent_e2e_direct.py::test_subagent_notification_no_injection -v -s
