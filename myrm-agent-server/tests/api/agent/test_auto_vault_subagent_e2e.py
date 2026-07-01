"""E2E: subagent large bash output triggers auto-vault in parent tool result."""

from __future__ import annotations

import json
import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _stream_until_done(client: TestClient, req: dict) -> list[dict]:
    events: list[dict] = []
    resume_value = None
    query = req.get("query", "")
    chat_id = req["chatId"]
    message_id = req["messageId"]

    for _round in range(8):
        body = {
            **req,
            "query": query if resume_value is None else "",
            "chatId": chat_id,
            "messageId": message_id,
            "modelSelection": get_model_selection(),
            "actionMode": "general",
        }
        if resume_value is not None:
            body["resumeValue"] = {"decisions": resume_value}

        finished = False
        with client.stream("POST", "/api/v1/agents/agent-stream", json=body) as response:
            assert response.status_code == 200, response.read().decode()
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                events.append(data)
                etype = data.get("type")
                if etype == "approval_required":
                    payload = data.get("data") or {}
                    if payload.get("action_type") == "subagent_approval":
                        resume_value = [{"type": "approve", "feedback": "auto-approve subagent bash"}]
                        message_id = str(uuid.uuid4())
                        break
                    resume_value = [{"type": "approve", "feedback": "auto-approve delegate"}]
                    message_id = str(uuid.uuid4())
                    break
                if etype == "message_end":
                    finished = True
                    break
            else:
                if resume_value is None:
                    finished = True
        if finished and resume_value is None:
            break
        if resume_value is not None:
            query = ""
            continue
        break

    check_e2e_errors(events)
    return events


@pytest.mark.e2e
@pytest.mark.skipif(not os.environ.get("BASIC_API_KEY"), reason="E2E requires BASIC_API_KEY")
def test_subagent_large_output_surfaces_vault_pointer(client: TestClient) -> None:
    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    query = (
        "你必须使用 delegate_task_tool，agent_type 设为 test_bash，wait=true。"
        "task 内容：执行 bash 命令 python3 -c \"print('AUTO_VAULT_E2E_' + 'x'*9000)\"。"
        "子 Agent 返回后，你在回复里原样输出其中出现的 vault:// 指针（如有）。"
        "必须使用原生 function calling，禁止在正文写 XML 工具调用。"
    )
    req = {
        "query": query,
        "chatId": chat_id,
        "messageId": message_id,
        "jitSubagents": {
            "test_bash": {
                "system_prompt": "You are a bash worker. Run the requested command and return stdout.",
                "tools": ["bash_code_execute_tool"],
                "config": {"auto_vault_threshold": 500},
            }
        },
    }

    events = _stream_until_done(client, req)
    blob = json.dumps(events, ensure_ascii=False)
    assert "vault://" in blob or "AUTO_VAULT_E2E_" in blob, "Expected vault pointer or large marker in stream"
    if "vault://" in blob:
        assert re.search(r"vault://[a-f0-9-]+", blob) is not None
