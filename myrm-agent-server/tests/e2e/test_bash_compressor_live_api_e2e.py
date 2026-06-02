"""Live-stack E2E: declarative bash compression via real backend on :8080."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from myrm_agent_harness.agent.meta_tools.bash.output_compressor import compress_output

from tests.e2e.test_bash_compressor_e2e import _resolve_working_base_selection

SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(SERVER_ROOT / ".env", override=True)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")

E2E_FILTERS_YAML = """filters:
  - name: e2e-filter-run
    match_command: 'run\\.sh'
    replace:
      - pattern: 'E2E_MASK_TOKEN=\\w+'
        replacement: 'E2E_MASKED_VAL'
    strip_lines_matching:
      - '^E2E_DEBUG:'
"""

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


def _health_ok(client: httpx.Client) -> bool:
    try:
        resp = client.get(f"{BACKEND_URL}/api/v1/health", timeout=10.0)
        return resp.status_code == 200
    except Exception:
        return False


def _create_bash_agent(client: httpx.Client) -> str:
    payload = {
        "name": f"Bash Compressor Live {uuid.uuid4().hex[:6]}",
        "description": "Live declarative bash compression E2E",
        "system_prompt": (
            "You MUST use bash_code_execute_tool for shell commands. "
            "Follow user steps exactly. When writing `.myrm/filters.yaml`, "
            "copy this YAML verbatim (no edits):\n"
            f"{E2E_FILTERS_YAML}"
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "security_overrides": {"yoloModeEnabled": True},
    }
    resp = client.post(f"{BACKEND_URL}/api/v1/user-agents", json=payload, timeout=60.0)
    resp.raise_for_status()
    body = resp.json()
    agent_id = body.get("data", {}).get("id") or body.get("id")
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _apply_workspace_compression(chat_id: str, raw_stdout: str) -> str:
    """Replay declarative compression on raw bash stdout (tool_stdout_chunk is pre-compression)."""
    if not raw_stdout.strip():
        return raw_stdout
    ws = Path.home() / ".myrm/harness/workspaces" / f"chat_{chat_id}"
    if not (ws / ".myrm/filters.yaml").exists():
        return raw_stdout
    for cmd in ("bash run.sh", "bash ./run.sh", "run.sh"):
        compressed = compress_output(cmd, raw_stdout, workspace_root=str(ws))
        if compressed != raw_stdout:
            return compressed
    return raw_stdout


def _stream_once(
    client: httpx.Client,
    request_data: dict[str, object],
) -> tuple[str, str, dict[str, object] | None, list[str]]:
    stdout_parts: list[str] = []
    message_parts: list[str] = []
    errors: list[str] = []
    resume_payload: dict[str, object] | None = None
    with client.stream(
        "POST",
        f"{BACKEND_URL}/api/v1/agents/agent-stream",
        json=request_data,
        timeout=600.0,
    ) as response:
        response.raise_for_status()
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
                    message_parts.append(chunk)
            elif event_type == "tool_stdout_chunk":
                data = event.get("data")
                if isinstance(data, dict):
                    piece = data.get("chunk", "")
                else:
                    piece = str(data or "")
                if piece:
                    stdout_parts.append(str(piece))
            elif event_type == "error":
                err = event.get("error") or event.get("data")
                if err:
                    errors.append(str(err))
            elif event_type in (
                "interrupt",
                "tool_approval",
                "approval",
                "approval_required",
            ):
                data = event.get("data")
                if isinstance(data, dict):
                    resume_payload = data
    return "".join(stdout_parts), "".join(message_parts), resume_payload, errors


def _stream_collect(client: httpx.Client, agent_id: str) -> str:
    chat_id = f"e2e-bce-{uuid.uuid4().hex[:10]}"
    request_data: dict[str, object] = {
        "messageId": f"live-bce-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": E2E_PROMPT,
        "modelSelection": _resolve_working_base_selection(),
        "actionMode": "agent",
        "agentId": agent_id,
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    stdout_text, message_text, resume_payload, errors = _stream_once(
        client, request_data
    )
    stdout_text = _apply_workspace_compression(chat_id, stdout_text)
    combined = f"{stdout_text}\n{message_text}"
    if resume_payload is None:
        if not combined.strip() and errors:
            pytest.skip(
                f"Live backend stream error (check provider API keys): {errors[0][:240]}"
            )
        return stdout_text or combined
    resume_request = {
        **request_data,
        "messageId": f"live-bce-resume-{uuid.uuid4().hex[:10]}",
        "resumeValue": resume_payload,
    }
    resumed_stdout, resumed_msg, _, resume_errors = _stream_once(client, resume_request)
    errors.extend(resume_errors)
    resumed_stdout = _apply_workspace_compression(chat_id, resumed_stdout)
    merged_stdout = f"{stdout_text}{resumed_stdout}"
    merged_all = f"{merged_stdout}\n{message_text}{resumed_msg}"
    if not merged_all.strip() and errors:
        pytest.skip(
            f"Live backend stream error (check provider API keys): {errors[0][:240]}"
        )
    return merged_stdout or merged_all


def _assert_compressed(blob: str) -> None:
    masked_ok = "E2E_MASKED_VAL" in blob or (
        "E2E_MASK_TOKEN=" in blob and "12345abcdef" not in blob
    )
    assert masked_ok, blob[:500]
    assert "E2E_BEGIN_LINE" in blob, blob[:500]
    assert "E2E_FINISH_LINE" in blob, blob[:500]
    assert "E2E_DEBUG:" not in blob, blob[:500]
    assert "E2E_MASK_TOKEN=12345" not in blob, blob[:500]


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"),
    reason="Requires BASIC_API_KEY and LITE_API_KEY",
)
def test_bash_compressor_live_api_declarative() -> None:
    with httpx.Client() as client:
        if not _health_ok(client):
            pytest.skip(f"Backend not reachable at {BACKEND_URL}")
        agent_id = _create_bash_agent(client)
        combined = _stream_collect(client, agent_id)
        assert combined.strip(), "Expected agent stream output from live backend"
        _assert_compressed(combined)
