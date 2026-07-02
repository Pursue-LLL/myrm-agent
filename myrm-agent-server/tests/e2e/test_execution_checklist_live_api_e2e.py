"""Live-stack E2E: Task Tracking (execution checklist) via real backend :8080."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

from tests.api.agent.utils import check_e2e_errors, get_model_selection, get_search_service_config

SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(SERVER_ROOT / ".env.test", override=True)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")


def _health_ok(client: httpx.Client) -> bool:
    try:
        resp = client.get(f"{BACKEND_URL}/api/v1/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


def _stream_task_tracking(client: httpx.Client, query: str) -> tuple[str, list[dict[str, object]]]:
    request_data: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "chatId": f"tsm-live-{uuid.uuid4().hex[:8]}",
        "query": query,
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
        "actionMode": "agent",
        "agentConfig": {
            "skill_ids": [],
            "enabled_builtin_tools": ["task_tracking"],
        },
    }

    collected: list[dict[str, object]] = []
    message_chunks: list[str] = []

    with client.stream(
        "POST",
        f"{BACKEND_URL}/api/v1/agents/agent-stream",
        json=request_data,
        timeout=180.0,
    ) as response:
        assert response.status_code == 200, response.read().decode("utf-8", errors="replace")
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            collected.append(data)
            if data.get("type") == "message" and data.get("data"):
                message_chunks.append(str(data["data"]))

    return "".join(message_chunks), collected


@pytest.mark.e2e
@pytest.mark.skipif(not os.environ.get("BASIC_API_KEY"), reason="E2E requires BASIC_API_KEY in .env.test")
class TestExecutionChecklistLiveE2E:
    def test_task_tracking_checklist_sse_on_live_backend(self) -> None:
        with httpx.Client(timeout=180.0) as client:
            if not _health_ok(client):
                pytest.skip(f"Live backend not reachable at {BACKEND_URL}")

            query = (
                "You MUST use update_execution_checklist_tool. "
                "Create a 3-item checklist (all pending), then mark item 1 completed, "
                "then item 2 completed, then item 3 completed. "
                "After all items are completed, reply with exactly: TSM_E2E_OK"
            )

            answer, events = _stream_task_tracking(client, query)
            assert len(events) > 0
            check_e2e_errors(events)

            checklist_steps = [
                e
                for e in events
                if e.get("type") == "tasks_steps"
                and (
                    e.get("step_key") == "checklist_root"
                    or str(e.get("step_key", "")).startswith("checklist_")
                    or e.get("tool_name") == "update_execution_checklist_tool"
                )
            ]
            assert len(checklist_steps) >= 1, "Expected checklist or tool tasks_steps on live backend"

            tool_steps = [
                e
                for e in events
                if e.get("type") == "tasks_steps" and e.get("tool_name") == "update_execution_checklist_tool"
            ]
            assert len(tool_steps) >= 1, "Expected update_execution_checklist_tool tasks_steps"

            assert any(e.get("type") in {"message_end", "message"} for e in events), (
                "Stream should emit message or message_end"
            )

            assert "TSM_E2E_OK" in answer.upper(), f"Expected TSM_E2E_OK in answer, got: {answer[:200]!r}"
