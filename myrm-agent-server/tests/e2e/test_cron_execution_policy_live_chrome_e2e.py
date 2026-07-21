"""Chrome E2E LIVE_AGENT: restricted cron job runs real LLM on private backend.

Uses ``private_backend=True`` so trigger/poll hit an isolated ``:180xx`` API — never
contends with shared ``:8080`` while parallel READ/LIVE pytest sessions run.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_cron_execution_policy_live_chrome_e2e.py
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402

_FORBIDDEN_TOOL_NAMES = frozenset(
    {
        "file_ops",
        "file_ops_tool",
        "glob_tool",
        "grep_tool",
        "code_execute",
        "code_execute_tool",
        "bash_code_execute_tool",
        "cron_manage_tool",
        "delegate_task_tool",
        "computer_use_tool",
    }
)
_WEB_TOOL_HINTS = frozenset({"web_search", "web_search_tool"})
_POLL_INTERVAL_SEC = 4.0
_RUN_DEADLINE_SEC = 300.0
_CRON_PROMPT = (
    "E2E_CRON_POLICY: Call web_search exactly once with query 'today UTC date'. "
    "Then reply with exactly: WEBONLY_OK"
)


def _cron_api(client: httpx.Client, api_base: str, method: str, path: str, **kwargs: object) -> dict[str, object]:
    response = client.request(method, f"{api_base}/api/v1/cron{path}", **kwargs)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError(f"Expected JSON object from cron API, got {type(body).__name__}")
    return body


def _tool_names_from_run(run: dict[str, object]) -> list[str]:
    metadata = run.get("metadata")
    if not isinstance(metadata, dict):
        return []
    steps = metadata.get("progressSteps")
    if not isinstance(steps, list):
        return []
    names: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        raw = step.get("tool_name") or step.get("toolName") or step.get("name")
        if isinstance(raw, str) and raw.strip():
            names.append(raw.strip())
    return names


def _create_restricted_job(client: httpx.Client, api_base: str) -> str:
    payload = {
        "name": f"e2e-cron-policy-live-{uuid.uuid4().hex[:10]}",
        "job_type": "agent",
        "schedule": {"kind": "interval", "interval_ms": 3_600_000},
        "prompt": _CRON_PROMPT,
        "agent_id": "builtin-developer",
        "required_capabilities": ["web_search_tool", "net_fetch"],
        "tools_allowed": ["web_search"],
        "timeout_seconds": 90,
        "session_target": "isolated",
    }
    job = _cron_api(client, api_base, "POST", "/", json=payload)
    job_id = job.get("id")
    assert isinstance(job_id, str) and job_id
    assert job.get("tools_allowed") == ["web_search"]
    assert job.get("required_capabilities") == ["web_search_tool", "net_fetch"]
    return job_id


def _wait_scheduler_ready(client: httpx.Client, api_base: str) -> None:
    deadline = time.monotonic() + 60.0
    last: dict[str, object] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"{api_base}/api/v1/cron/scheduler/health", timeout=15.0)
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                last = payload
                if payload.get("running") is True:
                    return
        time.sleep(2.0)
    raise AssertionError(f"Cron scheduler not ready on {api_base}: {last!r}")


def _trigger_and_wait(client: httpx.Client, api_base: str, job_id: str) -> dict[str, object]:
    _wait_scheduler_ready(client, api_base)
    _cron_api(client, api_base, "POST", f"/{job_id}/resume")
    triggered = _cron_api(client, api_base, "POST", f"/{job_id}/trigger")
    assert triggered.get("triggered") is True, f"trigger_now failed: {triggered!r}"

    deadline = time.monotonic() + _RUN_DEADLINE_SEC
    last_run: dict[str, object] | None = None
    last_job: dict[str, object] | None = None
    while time.monotonic() < deadline:
        job = _cron_api(client, api_base, "GET", f"/{job_id}")
        last_job = job
        runs = _cron_api(client, api_base, "GET", f"/{job_id}/runs?limit=3&offset=0")
        items = runs.get("items")
        if isinstance(items, list) and items:
            candidate = items[0]
            if isinstance(candidate, dict):
                last_run = candidate
                status = str(candidate.get("status", ""))
                if status not in {"running", "pending"}:
                    return candidate
        time.sleep(_POLL_INTERVAL_SEC)
    raise AssertionError(
        f"Cron run did not finish within {_RUN_DEADLINE_SEC}s; "
        f"last_run={last_run!r} job={last_job!r}"
    )


def _delete_job_best_effort(client: httpx.Client, api_base: str, job_id: str) -> None:
    try:
        client.delete(f"{api_base}/api/v1/cron/{job_id}", timeout=30.0)
    except httpx.HTTPError:
        pass


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.timeout(600)
def test_live_cron_webonly_policy_progress_steps() -> None:
    if not wait_e2e_provider_ready():
        pytest.fail("Provider config not ready — seed default model before LIVE cron E2E")

    api_base = get_e2e_api_url()
    job_id = ""
    with httpx.Client() as client:
        try:
            job_id = _create_restricted_job(client, api_base)
            run = _trigger_and_wait(client, api_base, job_id)
            status = str(run.get("status", ""))
            error = run.get("error")
            output = run.get("output")
            tool_names = _tool_names_from_run(run)

            assert status == "success", (
                f"Expected cron success, got status={status!r} error={error!r} output={output!r}"
            )
            forbidden = [name for name in tool_names if name in _FORBIDDEN_TOOL_NAMES]
            assert not forbidden, f"Forbidden tools in progressSteps: {forbidden}; all={tool_names}"
            if tool_names:
                assert any(
                    any(hint in name for hint in _WEB_TOOL_HINTS) for name in tool_names
                ), f"Expected web_search in progressSteps, got {tool_names}"
            output_text = output if isinstance(output, str) else ""
            assert "WEBONLY_OK" in output_text.upper(), (
                f"Expected WEBONLY_OK in output, got {output!r}"
            )
        finally:
            if job_id:
                _delete_job_best_effort(client, api_base, job_id)
