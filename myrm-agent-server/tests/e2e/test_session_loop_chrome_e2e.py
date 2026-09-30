"""Real Chrome MCP E2E and HTTP lifecycle integration for Session-Scoped /loop scheduler.

Covers:
  - Session loop start: POST /api/v1/chats/{id}/loop/start
  - Status verification: GET /api/v1/chats/{id}/loop/status -> active state, countdown, backoff
  - UI capsule presence: data-testid="session-loop-status-bar"
  - Stop action: POST /api/v1/chats/{id}/loop/stop -> transitions to stopped state
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import get_e2e_api_url  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _api_request(
    path: str, method: str = "GET", data: dict[str, object] | None = None
) -> dict[str, object] | None:
    url = f"{get_e2e_api_url()}{path}"
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"} if payload else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            return result if isinstance(result, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _is_backend_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{get_e2e_api_url()}/api/v1/health", timeout=5) as resp:  # noqa: S310
            return resp.status == 200
    except Exception:
        return False


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_session_loop_http_lifecycle_e2e() -> None:
    """Verifies end-to-end HTTP lifecycle of the session-scoped loop scheduler."""
    if not _is_backend_ready():
        pytest.skip("Backend is not ready for live E2E")

    chat_id = f"e2e-loop-test-{int(time.time())}"

    # 1. Status before start is none/inactive
    status_pre = _api_request(f"/api/v1/chats/{chat_id}/loop/status")
    assert status_pre is not None, "Failed to connect to backend loop status"
    data_pre = status_pre.get("data")
    assert isinstance(data_pre, dict)
    assert data_pre.get("is_active") is False
    assert data_pre.get("status") == "none"

    # 2. Start loop with 1m interval and 5 times limit
    start_resp = _api_request(
        f"/api/v1/chats/{chat_id}/loop/start",
        method="POST",
        data={"command": "/loop 1m check cluster telemetry --times 5"},
    )
    assert start_resp is not None, "Failed to start session loop"
    assert start_resp.get("success") is True
    data_start = start_resp.get("data")
    assert isinstance(data_start, dict)
    assert data_start.get("is_active") is True
    assert data_start.get("status") == "active"
    assert data_start.get("mode") == "interval"
    assert data_start.get("prompt") == "check cluster telemetry"
    assert data_start.get("times_limit") == 5

    # 3. Status shows active and has countdown
    status_active = _api_request(f"/api/v1/chats/{chat_id}/loop/status")
    assert status_active is not None
    data_active = status_active.get("data")
    assert isinstance(data_active, dict)
    assert data_active.get("is_active") is True
    assert data_active.get("prompt") == "check cluster telemetry"
    assert data_active.get("current_delay_human") == "1m"

    # 4. Stop loop with user reason
    stop_resp = _api_request(
        f"/api/v1/chats/{chat_id}/loop/stop",
        method="POST",
        data={"reason": "user_stopped"},
    )
    assert stop_resp is not None, "Failed to stop session loop"
    assert stop_resp.get("success") is True
    data_stop = stop_resp.get("data")
    assert isinstance(data_stop, dict)
    assert data_stop.get("is_active") is False
    assert data_stop.get("status") == "stopped"
    assert data_stop.get("last_stop_reason") == "user_stopped"

    # 5. Final status check confirms stopped
    status_final = _api_request(f"/api/v1/chats/{chat_id}/loop/status")
    assert status_final is not None
    data_final = status_final.get("data")
    assert isinstance(data_final, dict)
    assert data_final.get("is_active") is False
    assert data_final.get("status") == "stopped"

    # 6. Verify loop with --until condition parameter
    chat_id_until = f"e2e-loop-until-{int(time.time())}"
    start_until_resp = _api_request(
        f"/api/v1/chats/{chat_id_until}/loop/start",
        method="POST",
        data={"command": "/loop 2m tail logs --until error rate drops below 1%"},
    )
    assert start_until_resp is not None
    assert start_until_resp.get("success") is True
    data_until = start_until_resp.get("data")
    assert isinstance(data_until, dict)
    assert data_until.get("is_active") is True
    assert data_until.get("prompt") == "tail logs"
    assert data_until.get("until_condition") == "error rate drops below 1%"
    assert data_until.get("current_delay_human") == "2m"

    # Clean up until loop
    stop_until_resp = _api_request(
        f"/api/v1/chats/{chat_id_until}/loop/stop",
        method="POST",
        data={"reason": "user_stopped"},
    )
    assert stop_until_resp is not None
    assert stop_until_resp.get("success") is True


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_session_loop_ui_capsule_and_stop_chrome_e2e() -> None:
    """Verifies Chrome WebUI renders LoopStatusBar capsule and responds to stop button."""
    if not _is_backend_ready():
        pytest.skip("Backend is not ready for live E2E")

    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")

    chat_id = f"e2e-ui-loop-{int(time.time())}"
    start_res = _api_request(
        f"/api/v1/chats/{chat_id}/loop/start",
        method="POST",
        data={"command": "/loop 3m cluster telemetry monitoring --times 5 --until zero failure"},
    )
    assert start_res is not None and start_res.get("success") is True

    try:
        with open_mcp_page(f"{get_e2e_ui_url()}/chat/{chat_id}") as (client, page):
            # Dispatch event to notify useLoopStatus of newly activated loop
            client.evaluate(
                page,
                f"window.dispatchEvent(new CustomEvent('session-loop-changed', {{ detail: {{ chatId: '{chat_id}' }} }}));",
                timeout_sec=10.0,
            )

            # Wait for capsule to render in DOM
            bar_state = wait_for_state(
                client,
                page,
                """(() => {
                    const el = document.querySelector('[data-testid="session-loop-status-bar"]');
                    if (!el) return { ready: false };
                    const text = el.textContent || '';
                    const hasUntil = !!el.querySelector('[data-testid="loop-until-badge"]');
                    const hasStop = !!el.querySelector('[data-testid="stop-session-loop-btn"]');
                    return { ready: true, text, hasUntil, hasStop };
                })()""",
                timeout_sec=30.0,
            )
            assert bar_state.get("ready") is True, f"LoopStatusBar not visible: {bar_state}"
            assert bar_state.get("hasUntil") is True, "Target condition badge missing"
            assert bar_state.get("hasStop") is True, "Stop button missing"
            assert "cluster telemetry" in str(bar_state.get("text")), f"Prompt missing: {bar_state}"

            # Click stop button via DOM action
            stopped_eval = client.evaluate(
                page,
                """(() => {
                    const btn = document.querySelector('[data-testid="stop-session-loop-btn"]');
                    if (!btn) return { clicked: false };
                    btn.click();
                    return { clicked: true };
                })()""",
                timeout_sec=10.0,
            )
            assert isinstance(stopped_eval, dict) and stopped_eval.get("clicked") is True

            # Verify API confirms loop transition to stopped
            time.sleep(1.0)
            status = _api_request(f"/api/v1/chats/{chat_id}/loop/status")
            assert status is not None
            data = status.get("data")
            assert isinstance(data, dict)
            assert data.get("is_active") is False
            assert data.get("status") == "stopped"
            assert data.get("last_stop_reason") == "user_stopped"
    finally:
        _api_request(
            f"/api/v1/chats/{chat_id}/loop/stop",
            method="POST",
            data={"reason": "cleanup"},
        )
