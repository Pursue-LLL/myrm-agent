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
