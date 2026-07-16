"""Real Chrome MCP E2E for viewing and cancelling a running subagent."""

from __future__ import annotations

import json
import os
import selectors
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state
from tests.support.e2e_runtime_guard import E2EResourceLedger

_AGENT_ROOT = Path(__file__).resolve().parents[3]
_PREPARE = _AGENT_ROOT / "scripts/dev/subagent-dashboard-e2e-prepare.mjs"
_PREPARE_PREFIX = "E2E_PREPARE_JSON="


def _read_prepare_result(process: subprocess.Popen[str], timeout_sec: float) -> dict[str, object]:
    if process.stdout is None:
        raise RuntimeError("Subagent prepare stdout is unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_sec
    diagnostics: list[str] = []
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                remainder = process.stdout.read()
                if remainder:
                    diagnostics.extend(remainder.splitlines())
                raise RuntimeError(f"Subagent prepare exited {process.returncode}: {diagnostics[-20:]}")
            events = selector.select(timeout=min(1.0, deadline - time.monotonic()))
            if not events:
                continue
            line = process.stdout.readline().strip()
            if not line:
                continue
            if line.startswith(_PREPARE_PREFIX):
                payload = json.loads(line.removeprefix(_PREPARE_PREFIX))
                if not isinstance(payload, dict):
                    raise RuntimeError(f"Invalid subagent prepare payload: {payload!r}")
                return payload
            diagnostics.append(line)
    finally:
        selector.close()
    raise TimeoutError(f"Subagent prepare timed out: {diagnostics[-20:]}")


@pytest.fixture
def running_subagent(
    e2e_resource_ledger: E2EResourceLedger,
) -> Iterator[dict[str, object]]:
    if shutil.which("bun") is None:
        pytest.skip("bun is required for subagent dashboard prepare")
    if not os.environ.get("BASIC_API_KEY", "").strip() or not os.environ.get("BASIC_MODEL", "").strip():
        pytest.skip("BASIC_API_KEY and BASIC_MODEL are required")
    env = os.environ.copy()
    env["E2E_HOLD_MS"] = "90000"
    env["WAVE_LEDGER_LEASE_ID"] = e2e_resource_ledger.lease_id
    env["WAVE_LEDGER_NAMESPACE"] = e2e_resource_ledger.namespace
    process = subprocess.Popen(
        ["bun", str(_PREPARE)],
        cwd=str(_AGENT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        yield _read_prepare_result(process, timeout_sec=210.0)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.chrome_e2e(lane="LIVE_AGENT")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_lists_and_cancels_running_task(
    running_subagent: dict[str, object],
) -> None:
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")

    with open_mcp_page(ui_url) as (client, page):
        trigger = wait_for_state(
            client,
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              return { ready: !!button };
            })()""",
            timeout_sec=60.0,
        )
        assert trigger["ready"] is True
        clicked = client.evaluate(
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              if (!button) return false;
              button.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert clicked is True
        row = wait_for_state(
            client,
            page,
            f"""(() => {{
              const cancel = document.querySelector('[data-testid="subagent-cancel-btn"]');
              const text = document.body.innerText || '';
              return {{ ready: !!cancel && text.includes({task_id!r}), text }};
            }})()""",
        )
        assert task_id in str(row.get("text") or "")
        cancelled = client.evaluate(
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-cancel-btn"]');
              if (!button) return false;
              button.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert cancelled is True
        verified = wait_for_state(
            client,
            page,
            f"""(async () => {{
              const response = await fetch('/api/v1/chats/{chat_id}/subagents/{task_id}/cancel', {{
                method: 'POST',
              }});
              return {{ ready: response.status === 404, status: response.status }};
            }})()""",
        )
        assert verified.get("status") == 404
