"""Adversarial Verifier E2E API Test

Tests the Adversarial Verifier orchestration using the Chat API.
"""

import json
import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from tests.api.agent.utils import get_model_selection


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def perform_verifier_task(
    client: TestClient,
    query: str,
    *,
    engine_params: dict[str, object] | None = None,
) -> tuple[str, list[dict[str, object]], int]:
    """Execute a task that requires verification and collect stream."""

    model_selection = get_model_selection()

    import uuid

    request_payload: dict[str, object] = {
        "messageId": f"verify-msg-{uuid.uuid4().hex[:12]}",
        "chatId": f"verify-chat-{uuid.uuid4().hex[:10]}",
        "query": query,
        "modelSelection": model_selection,
        "actionMode": "agent",
    }
    if engine_params is not None:
        request_payload["engineParams"] = engine_params

    print(f"\n{'=' * 60}")
    print(f"🔍 Verifier Task: {query}")
    print(f"{'=' * 60}")

    collected_data: list[dict] = []
    message_chunks: list[str] = []
    tool_call_count = 0
    verification_events = 0

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_payload) as response:
        if response.status_code != 200:
            response.read()
            error_content = response.text
            print(f"\n❌ HTTP Error {response.status_code}: {error_content}")
        assert response.status_code == 200

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
                if data is None:
                    continue
                collected_data.append(data)
                event_type = data.get("type", "unknown")

                if event_type == "message":
                    content = data.get("data", "")
                    if content:
                        message_chunks.append(content)
                elif event_type == "subagent_start":
                    # Check if it's the verifier
                    agent_data = data.get("data", {})
                    description = agent_data.get("description", "")
                    print(f"  🤖 Subagent Start: {description}")
                    if (
                        "独立审查中" in description
                        or "Adversarial Verifier" in description
                        or "Adversarial Sandbox Verifier" in description
                    ):
                        verification_events += 1
                elif event_type == "tasks_steps":
                    tool_name = data.get("tool_name")
                    if tool_name:
                        tool_call_count += 1
                        print(f"  🔧 Tool Call: {tool_name}")
                elif event_type == "error":
                    error_msg = data.get("error", "")
                    print(f"  ❌ Error: {error_msg}")
            except json.JSONDecodeError as e:
                print(f"JSON Parse Error: {e}")

    full_answer = "".join(message_chunks)

    print(
        f"\n📊 Stats: Events={len(collected_data)}, Messages={len(message_chunks)}, Tools={tool_call_count}, Verifications={verification_events}"
    )

    return full_answer, collected_data, verification_events


def _build_verifier_mock_patches():
    from myrm_agent_harness.toolkits.llms.adapters.chat_model import ChatLiteLLM

    original_ainvoke = ChatLiteLLM.ainvoke

    async def mock_ainvoke_func(self, *args, **kwargs):
        messages = args[0] if args else kwargs.get("input", [])
        messages_str = str(messages)
        last_message = messages[-1] if messages else None

        import uuid

        from langchain_core.messages import AIMessage, ToolMessage

        first_msg_content = getattr(messages[0], "content", "") if messages else ""

        if "reviewing a recent Agent conversation" in messages_str:
            return await original_ainvoke(self, *args, **kwargs)
        if "Extract important user information" in messages_str:
            return await original_ainvoke(self, *args, **kwargs)

        if "Adversarial Sandbox Verifier" in messages_str:
            if isinstance(last_message, ToolMessage) and last_message.name == "submit_verdict":
                return AIMessage(content="Verification completed and verdict submitted.")
            return AIMessage(
                content="I have verified the output.",
                tool_calls=[
                    {
                        "name": "submit_verdict",
                        "args": {
                            "passed": True,
                            "summary": "The output is correct. STDOUT: Hello World",
                            "confidence": "HIGH",
                            "findings": [
                                {
                                    "description": "Printed Hello World correctly",
                                    "severity": "low",
                                }
                            ],
                        },
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                    }
                ],
            )

        if "Mock system prompt" in first_msg_content:
            return AIMessage(
                content=(
                    '<handover>\n{\n  "task_completed": ["wrote script"],\n'
                    '  "pending_todos": [],\n  "risks_or_notes": [],\n'
                    '  "relevant_files": []\n}\n</handover>\n'
                    "I have written and executed the python script. It printed Hello World."
                )
            )

        if "<identity>" in first_msg_content:
            if "I have written and executed the python script" in messages_str:
                return AIMessage(content="I have completed the task by delegating it.")
            return AIMessage(
                content="Delegating task as requested...",
                tool_calls=[
                    {
                        "name": "delegate_task_tool",
                        "args": {
                            "agent_type": "generalPurpose",
                            "objective": "Write a python script that prints Hello World and run it",
                            "wait": True,
                            "verifier_prompt": "Please verify the python script prints Hello World",
                        },
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                    }
                ],
            )

        return await original_ainvoke(self, *args, **kwargs)

    from myrm_agent_harness.toolkits.code_execution.executors.readonly_proxy import (
        ReadonlyExecutorProxy as _OriginalReadonlyExecutorProxy,
    )

    class _TestReadonlyExecutorProxy(_OriginalReadonlyExecutorProxy):
        def __init__(self, inner: object) -> None:
            super().__init__(inner)  # type: ignore[arg-type]
            self.has_executed_code = True

    async def mock_resolve(self, type_id: str):
        from myrm_agent_harness.agent.sub_agents.types import (
            SubagentConfig,
            WorkspacePolicy,
        )

        return SubagentConfig(
            system_prompt="Mock system prompt",
            workspace_policy=WorkspacePolicy.READ_ONLY_SANDBOX,
        )

    return (
        patch(
            "myrm_agent_harness.toolkits.llms.adapters.chat_model.ChatLiteLLM.ainvoke",
            new=mock_ainvoke_func,
        ),
        patch(
            "app.ai_agents.subagent_catalog.DatabaseSubagentCatalog.resolve",
            new=mock_resolve,
        ),
        patch(
            "myrm_agent_harness.toolkits.code_execution.executors.readonly_proxy.ReadonlyExecutorProxy",
            _TestReadonlyExecutorProxy,
        ),
    )


@contextmanager
def _verifier_mock_patches():
    p1, p2, p3 = _build_verifier_mock_patches()
    with p1, p2, p3:
        yield


def _assert_no_fatal_errors(collected_data: list[dict[str, object]]) -> None:
    error_events = [d for d in collected_data if d.get("type") == "error"]
    if not error_events:
        return
    error_msg = str(error_events[0].get("error", ""))
    if any(
        kw in error_msg
        for kw in [
            "Authentication",
            "Authorization",
            "timeout",
            "ServiceUnavailableError",
        ]
    ):
        pytest.skip(f"Environment/Network Error: {error_msg[:100]}")
    pytest.fail(f"Agent execution error: {error_msg}")


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestAdversarialVerifier:
    def test_verifier_execution(self, client: TestClient):
        """Test that the verifier correctly spawns and executes."""
        query = "请生成一个 Python 脚本来打印 Hello World，保存并运行它。"

        with _verifier_mock_patches():
            full_answer, collected_data, verification_events = perform_verifier_task(
                client,
                query,
                engine_params={"adversarial_verification": True},
            )

        assert len(collected_data) > 0, "Should have received events"
        _assert_no_fatal_errors(collected_data)
        assert verification_events > 0, "Expected Verifier to spawn and emit UI events"
        assert "PASS" in full_answer or "FAIL" in full_answer or len(full_answer) > 0
        print("\n✅ Test Passed: Adversarial Verifier E2E Execution")
