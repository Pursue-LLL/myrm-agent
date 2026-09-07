"""Live LLM E2E Task Flow: A2A delegation via agent-stream (Lane-C).

Validates that a real LLM recognizes registered A2A delegation tools,
generates a valid tool invocation to the authorized peer,
and integrates the remote peer's response into its final output.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection
from tests.support.test_secrets import apply_test_secrets_to_environ

apply_test_secrets_to_environ()


@pytest.mark.e2e
def test_a2a_delegation_task_flow_e2e(client: TestClient) -> None:
    """Validate full Task Flow: Agent A2A binding -> LLM tool call -> delegation -> output."""
    # 1. Register a trusted A2A peer via REST API
    peer_name = f"Quantum Research Peer {uuid.uuid4().hex[:6]}"
    peer_payload = {
        "name": peer_name,
        "base_url": "https://quantum.peer.internal",
        "description": "Specialized quantum physics simulation node",
        "auth_type": "bearer",
        "auth_token": "sk-secret-quantum-9988",
        "is_active": True,
    }
    peer_resp = client.post("/api/v1/a2a/peers", json=peer_payload)
    assert peer_resp.status_code == 201, f"Failed to create A2A peer: {peer_resp.text}"
    peer_id = peer_resp.json()["id"]

    # 2. Create an Agent with A2A enabled and whitelisted peer
    agent_payload = {
        "name": "Quantum Coordinator Agent",
        "description": "Orchestrates research via trusted A2A peers",
        "a2a_enabled": True,
        "a2a_trusted_peer_ids": [peer_id],
    }
    agent_resp = client.post("/api/agents", json=agent_payload)
    assert agent_resp.status_code == 200, f"Failed to create agent: {agent_resp.text}"
    agent_id = agent_resp.json()["data"]["id"]

    # Remote mock answer simulating the A2A endpoint response
    remote_expert_report = (
        "【量子退相干研究报告】通过动力学解耦脉冲序列（Dynamical Decoupling）"
        "并结合表面码纠错，可将超导量子比特相干时间有效延长3个数量级。"
    )

    try:
        # 3. Intercept remote A2A network hop to supply controlled expert response
        with patch(
            "myrm_agent_harness.toolkits.a2a.tools.execute_a2a_call",
            new_callable=AsyncMock,
        ) as mock_a2a_call:
            mock_a2a_call.return_value = {
                "success": True,
                "answer": remote_expert_report,
            }

            # 4. Initiate real LLM agent-stream task
            query = (
                f"请调用 a2a_call 工具，把「量子退相干抑制」任务委派给远端可信的研究助手节点（{peer_name}），"
                "并根据远端专家的返回，整理一份简明结论报告。禁止不调用工具直接回答。"
            )

            request_data = {
                "messageId": f"a2a-flow-msg-{uuid.uuid4().hex[:12]}",
                "chatId": f"a2a-flow-chat-{uuid.uuid4().hex[:10]}",
                "agentId": agent_id,
                "query": query,
                "modelSelection": get_model_selection(),
                "actionMode": "agent",
                "memoryRequireConfirmation": False,
                "enableMemoryAutoExtraction": False,
            }

            collected_data: list[dict[str, object]] = []
            message_chunks: list[str] = []
            tool_called_names: list[str] = []

            with client.stream(
                "POST",
                "/api/v1/agents/agent-stream",
                json=request_data,
                timeout=180.0,
            ) as response:
                assert response.status_code == 200

                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    try:
                        raw = json.loads(line[6:])
                        if not isinstance(raw, dict):
                            continue
                        collected_data.append(raw)
                        evt_type = raw.get("type", "")

                        if evt_type in ("message", "reasoning"):
                            content = raw.get("data", "")
                            if isinstance(content, str):
                                message_chunks.append(content)
                        elif evt_type == "tasks_steps":
                            t_name = raw.get("tool_name")
                            if isinstance(t_name, str):
                                tool_called_names.append(t_name)
                    except json.JSONDecodeError:
                        pass

            check_e2e_errors(collected_data)

            # 5. Assertions on Tool Call and Final Output
            # Verify the tool was actually invoked by LLM
            assert mock_a2a_call.await_count >= 1, (
                f"Expected a2a_call to be awaited by LLM. "
                f"Tools called: {tool_called_names}. Collected events: {len(collected_data)}"
            )

            # Verify credential injection and target URL resolution
            call_kwargs = mock_a2a_call.await_args.kwargs
            assert call_kwargs["peer_url"] == "https://quantum.peer.internal"
            assert call_kwargs["bearer_token"] == "sk-secret-quantum-9988"
            assert len(call_kwargs["prompt"]) > 0

            # Verify that final output integrated the remote expert answer
            full_answer = "".join(message_chunks)
            assert any(
                kw in full_answer
                for kw in ("量子", "退相干", "相干时间", "动力学解耦", "解耦")
            ), f"Final answer did not incorporate peer findings: {full_answer[:300]}"

    finally:
        # Cleanup Agent and Peer
        client.delete(f"/api/agents/{agent_id}")
        client.delete(f"/api/v1/a2a/peers/{peer_id}")
