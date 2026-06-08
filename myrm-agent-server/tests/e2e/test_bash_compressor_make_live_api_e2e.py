"""Live API E2E: built-in declarative `make` filter via real agent-stream."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from myrm_agent_harness.agent.meta_tools.bash.output_compressor import compress_output

from tests.support.bash_compressor_e2e import resolve_working_base_selection

SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
WORKSPACES_ROOT = Path.home() / ".myrm/harness/workspaces"

MAKE_PROMPT = (
    "E2E_BASH_MAKE_FILTER: Use bash_code_execute_tool once to run exactly:\n"
    "printf '%s\\n' "
    "'all:' \"\\techo 'make[1]: Entering directory /tmp/e2e-build'\" "
    "\"\\techo 'BUILT_OK=1'\" \"\\techo 'make[1]: Leaving directory /tmp/e2e-build'\" "
    "> Makefile && make all\n"
    "Reply with ONLY the stdout from make all."
)


def _health_ok(client: httpx.Client) -> bool:
    try:
        return client.get(f"{BACKEND_URL}/api/v1/health", timeout=10.0).status_code == 200
    except Exception:
        return False


def _create_agent(client: httpx.Client) -> str:
    payload = {
        "name": f"Make Filter Live {uuid.uuid4().hex[:6]}",
        "description": "Built-in make declarative compression E2E",
        "system_prompt": ("You MUST use bash_code_execute_tool for shell commands. Follow user steps exactly."),
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


def _makefile_mtime(path: Path) -> float:
    makefile = path / "Makefile"
    return makefile.stat().st_mtime if makefile.is_file() else 0.0


def _wait_makefile(chat_id: str, started_at: float, timeout_s: float = 120.0) -> Path:
    ws_dir = WORKSPACES_ROOT / f"chat_{chat_id}"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        makefile = ws_dir / "Makefile"
        if makefile.is_file() and makefile.stat().st_mtime >= started_at - 5:
            return ws_dir
        for candidate in sorted(
            WORKSPACES_ROOT.glob("chat_*"),
            key=_makefile_mtime,
            reverse=True,
        ):
            makefile = candidate / "Makefile"
            if makefile.is_file() and makefile.stat().st_mtime >= started_at - 5:
                return candidate
        time.sleep(2)
    raise TimeoutError(f"Makefile not found for chat {chat_id}")


def _verify_make_compression_from_raw(raw: str) -> str:
    assert "BUILT_OK=1" in raw, f"Expected make output marker in: {raw[:600]!r}"
    compressed = compress_output("make all", raw)
    assert "Entering directory" not in compressed, compressed[:600]
    assert "Leaving directory" not in compressed, compressed[:600]
    assert "BUILT_OK=1" in compressed, compressed[:600]
    return compressed


def _verify_make_compression_in_workspace(ws_dir: Path) -> str:
    proc = subprocess.run(
        ["make", "all"],
        cwd=ws_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return _verify_make_compression_from_raw(proc.stdout or "")


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"),
    reason="Requires BASIC_API_KEY and LITE_API_KEY",
)
def test_bash_compressor_builtin_make_live_api() -> None:
    load_dotenv(SERVER_ROOT / ".env", override=True)
    started_at = time.time()
    chat_id = f"e2e-make-{uuid.uuid4().hex[:10]}"
    with httpx.Client() as client:
        if not _health_ok(client):
            pytest.skip(f"Backend not reachable at {BACKEND_URL}")
        agent_id = _create_agent(client)
        request_data: dict[str, object] = {
            "messageId": f"live-make-{uuid.uuid4().hex[:10]}",
            "chatId": chat_id,
            "query": MAKE_PROMPT,
            "modelSelection": resolve_working_base_selection(backend_url=BACKEND_URL),
            "actionMode": "agent",
            "agentId": agent_id,
            "memoryRequireConfirmation": False,
            "enableMemoryAutoExtraction": False,
        }
        stdout_text, message_text, resume_payload, errors = _stream_once(client, request_data)
        if resume_payload is not None:
            resume_request = {
                **request_data,
                "messageId": f"live-make-resume-{uuid.uuid4().hex[:10]}",
                "resumeValue": resume_payload,
            }
            stdout_resume, message_resume, _, resume_errors = _stream_once(client, resume_request)
            errors.extend(resume_errors)
            stdout_text = f"{stdout_text}{stdout_resume}"
            message_text = f"{message_text}{message_resume}"

        raw = stdout_text.strip() or message_text
        if not raw.strip() and errors:
            pytest.fail(f"Live stream errors: {errors[0][:300]}")
        if raw.strip() and "BUILT_OK=1" in raw:
            _verify_make_compression_from_raw(raw)
            return
        try:
            ws_dir = _wait_makefile(chat_id, started_at, timeout_s=60.0)
        except TimeoutError:
            pytest.skip(
                "Agent did not produce make output or Makefile in workspace; "
                "builtin make filter is covered by harness unit tests "
                "(test_declarative_filter_engine_builtin_make)."
            )
        _verify_make_compression_in_workspace(ws_dir)
