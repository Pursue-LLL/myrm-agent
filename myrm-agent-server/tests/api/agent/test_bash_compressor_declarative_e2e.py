"""Real LLM agent-stream E2E: declarative bash output compression in the execution path."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from tests.support.bash_compressor_e2e import (
    E2E_FILTERS_YAML,
    apply_workspace_compression,
    resolve_working_base_selection,
)

SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

E2E_PROMPT = (
    "E2E_BASH_COMPRESSOR_RUN: In the workspace sandbox, do exactly:\n"
    "1. mkdir -p .myrm\n"
    "2. Write `.myrm/filters.yaml` with:\n"
    "filters:\n"
    "  - name: e2e-filter-run\n"
    "    match_command: 'run\\\\.sh'\n"
    "    replace:\n"
    "      - pattern: 'E2E_MASK_TOKEN=\\w+'\n"
    "        replacement: 'E2E_MASKED_VAL'\n"
    "    strip_lines_matching:\n"
    "      - '^E2E_DEBUG:'\n"
    "3. Write `run.sh`:\n"
    "#!/bin/bash\n"
    "echo 'E2E_BEGIN_LINE ok'\n"
    "echo 'E2E_DEBUG: loading config'\n"
    "echo 'E2E_MASK_TOKEN=12345abcdef'\n"
    "echo 'E2E_FINISH_LINE ok'\n"
    "4. Run `bash run.sh` using bash_code_execute_tool only.\n"
    "Reply with ONLY the raw stdout from step 4."
)


def _parse_stream_lines(
    client: TestClient,
    request_data: dict[str, object],
) -> tuple[str, str, dict[str, object] | None]:
    message_chunks: list[str] = []
    stdout_chunks: list[str] = []
    resume_payload: dict[str, object] | None = None

    with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=request_data,
        timeout=600.0,
    ) as response:
        assert response.status_code == 200, response.text
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if event is None:
                continue

            event_type = event.get("type")
            if event_type in ("message", "reasoning"):
                chunk = event.get("data", "")
                if isinstance(chunk, str) and chunk:
                    message_chunks.append(chunk)
            elif event_type == "tool_stdout_chunk":
                data = event.get("data")
                if isinstance(data, dict):
                    piece = data.get("chunk", "")
                else:
                    piece = str(data or "")
                if piece:
                    stdout_chunks.append(piece)
            elif event_type in ("interrupt", "tool_approval", "approval"):
                data = event.get("data")
                if isinstance(data, dict):
                    resume_payload = data

    return "".join(stdout_chunks), "".join(message_chunks), resume_payload


def _collect_stream(client: TestClient, query: str, agent_id: str | None) -> tuple[str, str]:
    chat_id = f"bce-api-{uuid.uuid4().hex[:10]}"
    request_data: dict[str, object] = {
        "messageId": f"bce-{uuid.uuid4().hex[:12]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": resolve_working_base_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    if agent_id:
        request_data["agentId"] = agent_id

    stdout_text, message_text, resume_payload = _parse_stream_lines(client, request_data)
    stdout_text = apply_workspace_compression(chat_id, stdout_text)
    if resume_payload is None:
        return stdout_text, message_text

    resume_request = {
        **request_data,
        "messageId": f"bce-resume-{uuid.uuid4().hex[:10]}",
        "resumeValue": resume_payload,
    }
    stdout_resume, message_resume, _ = _parse_stream_lines(client, resume_request)
    stdout_resume = apply_workspace_compression(chat_id, stdout_resume)
    return f"{stdout_text}{stdout_resume}", f"{message_text}{message_resume}"


def _create_bash_agent(client: TestClient) -> str:
    payload = {
        "name": f"Bash Compressor E2E {uuid.uuid4().hex[:6]}",
        "description": "Declarative bash compression E2E agent",
        "system_prompt": (
            "You are a bash execution agent. You MUST use bash_code_execute_tool for shell "
            "commands. Follow the user steps exactly. When writing `.myrm/filters.yaml`, "
            "copy this YAML verbatim (no edits):\n"
            f"{E2E_FILTERS_YAML}"
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "security_overrides": {"yoloModeEnabled": True},
    }
    response = client.post("/api/agents", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    agent_id = body.get("data", {}).get("id") or body.get("id")
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _assert_compressed_output(blob: str) -> None:
    masked_ok = "E2E_MASKED_VAL" in blob or ("E2E_MASK_TOKEN=" in blob and "12345abcdef" not in blob)
    assert masked_ok, f"Expected masked token in: {blob[:800]!r}"
    assert "E2E_BEGIN_LINE" in blob, f"Expected begin line in: {blob[:800]!r}"
    assert "E2E_FINISH_LINE" in blob, f"Expected finish line in: {blob[:800]!r}"
    assert "E2E_DEBUG:" not in blob, f"Expected DEBUG stripped in: {blob[:800]!r}"
    assert "E2E_MASK_TOKEN=12345" not in blob, f"Raw token leaked in: {blob[:800]!r}"


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"),
    reason="Requires BASIC_API_KEY and LITE_API_KEY in myrm-agent-server/.env.test",
)
def test_bash_compressor_agent_stream_declarative_filter(client: TestClient) -> None:
    load_dotenv(os.path.join(SERVER_ROOT, ".env"), override=True)
    agent_id = _create_bash_agent(client)
    stdout_text, message_text = _collect_stream(client, E2E_PROMPT, agent_id)
    combined = f"{stdout_text}\n{message_text}"
    assert combined.strip(), "Expected non-empty agent stream output"
    _assert_compressed_output(combined)
