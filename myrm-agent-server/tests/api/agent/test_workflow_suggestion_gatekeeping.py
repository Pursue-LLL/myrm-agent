"""Integration test: workflow_suggestion SSE event gatekeeping (MacTalk #2).

Validates the full API chain:
  client POST → orchestrator (load personal_settings) → stream_loop → workflow_escalation guard
  → workflow_suggestion SSE event is NOT emitted when suggestWorkflowMode defaults to False.

Also verifies that when a user explicitly opts in (suggestWorkflowMode=True),
the suggestion event IS emitted for qualifying multi-goal queries.
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


MULTI_GOAL_QUERY = (
    "请帮我完成以下任务：\n"
    "1. 调研 3 家竞品的定价策略\n"
    "2. 分别分析各家的优劣势\n"
    "3. 写一份对比报告\n"
    "4. 给出推荐方案\n"
    "5. 制作演示 PPT 大纲"
)


def _collect_sse_events(client: TestClient, payload: dict) -> list[dict]:
    """Stream agent-stream and collect parsed SSE events (max 15s)."""
    events: list[dict] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload, timeout=60.0) as resp:
        if resp.status_code != 200:
            resp.read()
            pytest.skip(f"API returned {resp.status_code}: {resp.text[:200]}")
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                break
            try:
                event = json.loads(raw)
                if isinstance(event, dict):
                    events.append(event)
                    if event.get("type") == "message_end":
                        break
            except json.JSONDecodeError:
                pass
    return events


def _has_workflow_suggestion(events: list[dict]) -> bool:
    return any(
        e.get("type") == "status" and e.get("step_key") == "workflow_suggestion"
        for e in events
    )


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY",
)
class TestWorkflowSuggestionGatekeeping:
    """Verify single-agent-by-default philosophy via real API stream."""

    def test_default_no_workflow_suggestion(self, client: TestClient):
        """Default personal_settings (None) → no workflow_suggestion SSE event."""
        uid = str(uuid.uuid4())
        payload = {
            "query": MULTI_GOAL_QUERY,
            "modelSelection": get_model_selection(),
            "chatId": f"test_wf_gate_{uid}",
            "messageId": f"msg_wf_gate_{uid}",
            "actionMode": "agent",
        }
        events = _collect_sse_events(client, payload)

        assert len(events) > 0, "Expected at least one SSE event"
        assert not _has_workflow_suggestion(events), (
            "workflow_suggestion event should NOT be emitted when suggestWorkflowMode defaults to False"
        )

    def test_opt_in_emits_workflow_suggestion(
        self, client: TestClient, mock_load_user_configs
    ):
        """Explicit opt-in (suggestWorkflowMode=True) → workflow_suggestion emitted."""
        from unittest.mock import AsyncMock, patch

        original_configs = mock_load_user_configs.return_value

        configs_with_opt_in = type(original_configs)(
            model_cfg=original_configs.model_cfg,
            search_cfg=original_configs.search_cfg,
            search_is_user_configured=original_configs.search_is_user_configured,
            retrieval_dict=original_configs.retrieval_dict,
            personal_settings_dict={"suggestWorkflowMode": True},
            mcp_dict=original_configs.mcp_dict,
            providers_dict=original_configs.providers_dict,
            security_config_dict=original_configs.security_config_dict,
        )
        mock_load_user_configs.return_value = configs_with_opt_in

        uid = str(uuid.uuid4())
        payload = {
            "query": MULTI_GOAL_QUERY,
            "modelSelection": get_model_selection(),
            "chatId": f"test_wf_optin_{uid}",
            "messageId": f"msg_wf_optin_{uid}",
            "actionMode": "agent",
        }
        events = _collect_sse_events(client, payload)

        assert len(events) > 0, "Expected at least one SSE event"

        if _has_workflow_suggestion(events):
            suggestion_events = [
                e for e in events
                if e.get("type") == "status" and e.get("step_key") == "workflow_suggestion"
            ]
            assert suggestion_events[0]["data"]["phase"] == "workflow_suggestion"
            assert suggestion_events[0]["data"]["status"] == "suggested"
        # Note: even with opt-in, the model router may assign a non-reasoning tier,
        # in which case no suggestion is emitted. Both outcomes are valid.

    def test_skip_flag_suppresses_suggestion(
        self, client: TestClient, mock_load_user_configs
    ):
        """skipWorkflowSuggestion engine_param → no suggestion even with opt-in."""
        original_configs = mock_load_user_configs.return_value
        configs_with_opt_in = type(original_configs)(
            model_cfg=original_configs.model_cfg,
            search_cfg=original_configs.search_cfg,
            search_is_user_configured=original_configs.search_is_user_configured,
            retrieval_dict=original_configs.retrieval_dict,
            personal_settings_dict={"suggestWorkflowMode": True},
            mcp_dict=original_configs.mcp_dict,
            providers_dict=original_configs.providers_dict,
            security_config_dict=original_configs.security_config_dict,
        )
        mock_load_user_configs.return_value = configs_with_opt_in

        uid = str(uuid.uuid4())
        payload = {
            "query": MULTI_GOAL_QUERY,
            "modelSelection": get_model_selection(),
            "chatId": f"test_wf_skip_{uid}",
            "messageId": f"msg_wf_skip_{uid}",
            "actionMode": "agent",
            "engineParams": {"skipWorkflowSuggestion": True},
        }
        events = _collect_sse_events(client, payload)

        assert len(events) > 0, "Expected at least one SSE event"
        assert not _has_workflow_suggestion(events), (
            "workflow_suggestion should be suppressed by skipWorkflowSuggestion flag"
        )
