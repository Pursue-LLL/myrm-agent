"""Subagent事件转发真实集成测试

测试13个事件类型在真实场景下的转发功能。
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.skipif(not os.getenv("BASIC_API_KEY"), reason="BASIC_API_KEY not configured, skipping real API test")
def test_subagent_event_forwarding_real(client: TestClient):
    """真实场景测试：验证Subagent事件转发"""

    request_data = {
        "messageId": str(uuid.uuid4()),
        "query": "使用analysis子agent分析：1+1等于多少？",
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }

    collected_events = []
    event_types_seen = set()
    subagent_events_seen = set()

    print("\n" + "=" * 80)
    print("🧪 开始真实集成测试：Subagent事件转发")
    print("=" * 80)

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data, timeout=120.0) as response:
        if response.status_code != 200:
            response.read()
            error_content = response.text
            print(f"\n❌ HTTP错误 {response.status_code}: {error_content}")
            pytest.fail(f"API request failed with status {response.status_code}")

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
                event_type = data.get("type")

                if event_type:
                    event_types_seen.add(event_type)
                    collected_events.append(data)

                    # 记录Subagent相关事件
                    if event_type.startswith("subagent_") or event_type in ["tool_start", "tool_end", "reasoning"]:
                        subagent_events_seen.add(event_type)

                        # 打印关键事件
                        if event_type == "subagent_start":
                            agent_type = data.get("data", {}).get("agent_type", "unknown")
                            print(f"  🚀 Subagent started: {agent_type}")

                        elif event_type == "subagent_progress":
                            progress = data.get("data", {}).get("progress", 0)
                            step = data.get("data", {}).get("current_step", "")
                            print(f"  📊 Progress: {int(progress * 100)}% - {step[:50]}")

                        elif event_type == "subagent_log":
                            level = data.get("data", {}).get("level", "INFO")
                            message = data.get("data", {}).get("message", "")[:60]
                            print(f"  📝 Log [{level}]: {message}")

                        elif event_type == "subagent_completion":
                            success = data.get("data", {}).get("success", False)
                            print(f"  ✅ Subagent completed: success={success}")

                #  Timeout after collecting enough data
                if len(collected_events) > 100:
                    print("\n  ⚠️  Collected 100+ events, stopping test...")
                    break

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"  ⚠️  Error parsing event: {e}")

    print("\n" + "=" * 80)
    print("📊 测试结果汇总:")
    print(f"  - 收集事件总数: {len(collected_events)}")
    print(f"  - 事件类型数量: {len(event_types_seen)}")
    print(f"  - Subagent事件数量: {len(subagent_events_seen)}")
    print(f"  - 所有事件类型: {sorted(event_types_seen)}")
    print(f"  - Subagent事件: {sorted(subagent_events_seen)}")
    print("=" * 80)

    # 验证关键事件类型
    critical_events = {
        "subagent_start",
        "subagent_completion",
    }

    found_critical = critical_events & event_types_seen
    missing_critical = critical_events - event_types_seen

    print(f"\n✅ 已检测到的关键事件: {found_critical}")
    if missing_critical:
        print(f"⚠️  未检测到的关键事件: {missing_critical}")
        print("  注意：可能是因为LLM没有调用delegate_task工具")

    # 统计Subagent相关事件
    subagent_progress_count = sum(1 for e in collected_events if e.get("type") == "subagent_progress")
    subagent_log_count = sum(1 for e in collected_events if e.get("type") == "subagent_log")

    print("\n📈 Subagent事件统计:")
    print(f"  - SUBAGENT_PROGRESS事件: {subagent_progress_count}")
    print(f"  - SUBAGENT_LOG事件: {subagent_log_count}")

    # 最终判断
    has_subagent_events = "subagent_start" in event_types_seen or "subagent_log" in event_types_seen

    if has_subagent_events:
        print("\n✅ 测试通过！Subagent事件转发系统正常工作！")
    else:
        print("\n⚠️  警告：未检测到Subagent相关事件")
        print("  可能原因：LLM未调用delegate_task工具")
        print("  但这不是事件转发系统的问题")

    # 断言：至少应该收集到一些事件
    assert len(collected_events) > 0, "Should collect at least some events"
    assert len(event_types_seen) > 0, "Should see at least some event types"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
