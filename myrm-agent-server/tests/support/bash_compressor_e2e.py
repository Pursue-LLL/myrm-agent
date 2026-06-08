"""Shared helpers for bash compressor live/API E2E tests."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx
from myrm_agent_harness.agent.meta_tools.bash.output_compressor import compress_output

from tests.api.agent.utils import get_lite_model_selection, get_model_selection

E2E_FILTERS_YAML = """filters:
  - name: e2e-filter-run
    match_command: 'run\\.sh'
    replace:
      - pattern: 'E2E_MASK_TOKEN=\\w+'
        replacement: 'E2E_MASKED_VAL'
    strip_lines_matching:
      - '^E2E_DEBUG:'
"""

_DEFAULT_BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")


def _probe_model_selection_works(
    selection: dict[str, object],
    *,
    backend_url: str = _DEFAULT_BACKEND_URL,
) -> bool:
    """Return True when agent-stream accepts the model selection."""
    payload = {
        "messageId": f"probe-{uuid.uuid4().hex[:8]}",
        "query": "Reply with exactly: PROBE_OK",
        "modelSelection": selection,
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    try:
        with httpx.Client(base_url=backend_url, timeout=90.0) as client:
            with client.stream(
                "POST",
                "/api/v1/agents/agent-stream",
                json=payload,
                timeout=90.0,
            ) as resp:
                if resp.status_code != 200:
                    return False
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if not event:
                        continue
                    event_type = event.get("type")
                    if event_type == "error":
                        err = str(event.get("error", ""))
                        if any(
                            token in err
                            for token in (
                                "Invalid API Key",
                                "401",
                                "Authentication",
                                "auth_permanent",
                            )
                        ):
                            return False
                    if event_type in ("message", "reasoning", "tool_stdout_chunk"):
                        data = event.get("data")
                        if data:
                            return True
                    if event_type == "message_end":
                        return True
    except Exception:
        return False
    return False


def resolve_working_base_selection(
    *,
    backend_url: str = _DEFAULT_BACKEND_URL,
) -> dict[str, object]:
    """Pick BASIC or LITE model selection that passes a live auth probe."""
    for _label, getter in (
        ("BASIC", get_model_selection),
        ("LITE", get_lite_model_selection),
    ):
        try:
            selection = getter()
        except Exception:
            continue
        if _probe_model_selection_works(selection, backend_url=backend_url):
            return selection
    raise RuntimeError("No working model API key in .env.test (probed BASIC_MODEL and LITE_MODEL)")


def apply_workspace_compression(chat_id: str, raw_stdout: str) -> str:
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
