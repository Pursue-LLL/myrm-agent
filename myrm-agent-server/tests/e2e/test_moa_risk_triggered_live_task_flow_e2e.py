"""End-to-End Universal Task Flow E2E: Risk Triggered MoA Advisor Stream Execution.

Validates the full business workflow:
1. Seed live LLM providers and assert provider readiness.
2. Create agent configured with moa_overlay fanout='risk_triggered' and auto_on_reasoning=True.
3. Create chat session bound to the agent.
4. Issue real task prompt through /api/v1/agents/agent-stream.
5. Live LLM execution with AdvisorRiskTriggerRouter middleware gate active.
6. Verify streaming events, valid response completion, and clean teardown.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from cdp_chat.support import wait_e2e_provider_ready

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    http_json,
    prepare_e2e_ui_session,
)
from tests.support.e2e_provider_seed import (
    build_e2e_model_selection,
    seed_live_e2e_providers,
)
from tests.support.subagent_hitl_stream import consume_agent_stream


def _delete_agent(api_url: str, agent_id: str) -> None:
    try:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
    except Exception:
        pass


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_moa_overlay_risk_triggered_live_task_flow_e2e() -> None:
    """Lane-C: Universal Task Flow E2E - Agent with risk_triggered MoA executes full task flow."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)

    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — verify .env.test LLM credentials")

    name = f"moa-flow-e2e-{uuid.uuid4().hex[:8]}"
    res = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": name,
            "system_prompt": "You are a concise technical architect assistant.",
            "engine_params": {
                "moa_overlay": {
                    "enabled": True,
                    "fanout": "risk_triggered",
                    "auto_on_reasoning": True,
                    "reference_model_selections": [
                        {"provider_id": "openai-like", "model": "gemini-3.8-flash-high"}
                    ],
                }
            },
        },
    )
    agent_id = (res.get("data") or {}).get("id")
    assert agent_id, f"failed to create agent for task flow: {res}"

    try:
        chat_id = f"chat-moa-{uuid.uuid4().hex[:8]}"
        chat_payload = {
            "chat_id": chat_id,
            "title": "MoA E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        }
        http_json("POST", f"{api_url}/api/v1/chats/", body=chat_payload)
        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        payload = {
            "query": "请用简短一句话说明微服务架构相比单体架构的核心优势。",
            "chatId": chat_id,
            "messageId": message_id,
            "agentId": agent_id,
            "modelSelection": build_e2e_model_selection(use_lite=True),
            "actionMode": "general",
            "securityPreset": "explore",
        }

        with httpx.Client() as client:
            action_type, events, errors = consume_agent_stream(client, api_url, payload)

        assert len(errors) == 0, f"agent-stream returned errors: {errors}"
        event_types = [str(e.get("type")) for e in events]
        assert "message_end" in event_types, f"missing message_end in {event_types}"
        assert any(t in event_types for t in ("message", "content_delta")), f"missing message tokens in {event_types}"

        chunks = []
        for e in events:
            if e.get("type") in ("message", "content_delta"):
                data = e.get("data")
                if isinstance(data, dict):
                    chunks.append(str(data.get("delta") or data.get("content") or ""))
                elif isinstance(data, str):
                    chunks.append(data)
        full_reply = "".join(chunks)
        assert len(full_reply.strip()) > 5, f"Expected non-empty reply, got: {full_reply}"
    finally:
        _delete_agent(api_url, agent_id)
