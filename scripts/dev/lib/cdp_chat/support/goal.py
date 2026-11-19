"""Goal status of a chat over the API.

[INPUT]
- cdp_chat.support.api_client::_e2e_api_get_json, _e2e_api_post_json, get_e2e_api_url (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)

[OUTPUT]
- GOAL_PERSISTED_STATUSES, is_persisted_e2e_goal: what counts as a persisted goal
- fetch_e2e_goal_status, wait_e2e_goal_status: read the goal of a chat once or until it persists
- post_goal_status_action, ensure_e2e_goal_active: drive the goal status

[POS]
Goal status of a chat over the API, the evidence the goal Chrome E2E asserts on.
"""

from __future__ import annotations

import time
import urllib.error

from cdp_chat.support.api_client import (
    _e2e_api_get_json,
    _e2e_api_post_json,
    get_e2e_api_url,
)

GOAL_PERSISTED_STATUSES = frozenset({"active", "budget_limited", "complete", "paused"})


def is_persisted_e2e_goal(goal: dict[str, object] | None) -> bool:
    """True when a goal record matches Goal Chrome E2E persistence assertions."""
    if goal is None:
        return False
    objective = str(goal.get("objective") or "").strip()
    status = str(goal.get("status") or "").strip()
    return bool(objective) and status in GOAL_PERSISTED_STATUSES


def fetch_e2e_goal_status(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> dict[str, object] | None:
    """Return the active goal dict for a chat session, or None if not yet persisted."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/goals/{chat_id}/status",
            timeout_sec=15.0,
        )
    except (OSError, TimeoutError, urllib.error.URLError, ValueError):
        return None
    goal = payload.get("goal") if isinstance(payload, dict) else None
    return goal if isinstance(goal, dict) else None


def wait_e2e_goal_status(
    chat_id: str,
    *,
    timeout_sec: float = 90.0,
    poll_interval_sec: float = 1.0,
    api_url: str | None = None,
) -> dict[str, object] | None:
    """Poll private-backend goal persistence (orchestrator may lag turn completion).

    Returns only records that pass ``is_persisted_e2e_goal`` — same bar as
    ``wait_turn_done`` okViaGoal and Goal Chrome E2E assertions.
    """
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        goal = fetch_e2e_goal_status(chat_id, api_url=api_url)
        if is_persisted_e2e_goal(goal):
            return goal
        time.sleep(poll_interval_sec)
    return None


def ensure_e2e_goal_active(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> dict[str, object]:
    """Normalize API goal to ACTIVE for B/D UI flows; fail fast on terminal states."""
    goal = fetch_e2e_goal_status(chat_id, api_url=api_url)
    if goal is None:
        return {"ok": False, "err": "no-goal"}

    status = str(goal.get("status") or "")
    if status in {"complete", "cancelled"}:
        return {
            "ok": False,
            "err": f"terminal-{status}",
            "status": status,
        }

    if status == "wait":
        unwait = post_goal_status_action(chat_id, "unwait", api_url=api_url)
        if unwait.get("new_status") != "active":
            return {"ok": False, "err": "unwait-failed", "payload": unwait}
        status = "active"

    if status in {"paused", "budget_limited", "needs_human_review", "pending_approval"}:
        resume = post_goal_status_action(chat_id, "resume", api_url=api_url)
        if resume.get("new_status") != "active":
            return {
                "ok": False,
                "err": "resume-failed",
                "payload": resume,
                "prior_status": status,
            }
        status = "active"

    if status != "active":
        return {"ok": False, "err": f"unexpected-status-{status}", "status": status}

    return {"ok": True, "status": "active"}


def post_goal_status_action(
    chat_id: str,
    action: str,
    *,
    api_url: str | None = None,
    note: str | None = None,
    wait_reason: str | None = None,
) -> dict[str, object]:
    """POST /api/v1/goals/{chat_id}/status for E2E setup/teardown."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    body: dict[str, object] = {"action": action}
    if note is not None:
        body["note"] = note
    if wait_reason is not None:
        body["wait_reason"] = wait_reason
    try:
        payload = _e2e_api_post_json(
            f"{resolved_api}/api/v1/goals/{chat_id}/status",
            body,
            timeout_sec=15.0,
        )
        return payload if isinstance(payload, dict) else {"value": payload}
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
