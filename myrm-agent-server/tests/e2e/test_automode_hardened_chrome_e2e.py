"""Chrome MCP E2E: Hardened AutoMode & Socially Irreversible Banner and Allowlist Gate.

Verifies end-to-end through the real Chrome UI:
1. Socially Irreversible action (git push) seeds approval card with amber irreversible banner,
   hiding the "Always Allow" button to prevent permanent allowlist bypass.
2. Auto Mode Suspended (3/20 circuit breaker) seeds approval card with red suspended banner,
   explaining that auto mode was halted due to consecutive denials.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)

_IRREVERSIBLE_BANNER_STATE = """(() => {
  const text = document.body?.innerText || '';
  const hasBanner = /不可逆|Socially Irreversible/i.test(text);
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasApprove = buttons.some((btn) => /Approve|批准/i.test(btn.textContent || ''));
  const hasAlwaysAllow = buttons.some((btn) => /Always Allow|Allow Always|始终允许/i.test(btn.textContent || ''));
  return {
    ready: hasBanner && hasApprove,
    hasBanner,
    hasApprove,
    hasAlwaysAllow,
    sample: text.slice(0, 800),
  };
})()"""

_SUSPENDED_BANNER_STATE = """(() => {
  const text = document.body?.innerText || '';
  const hasSuspended = /自动模式已自动挂起|Auto mode suspended/i.test(text);
  const hasReason = /连续 3 次|3 consecutive/i.test(text);
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasApprove = buttons.some((btn) => /Approve|批准|Override/i.test(btn.textContent || ''));
  return {
    ready: hasSuspended && hasReason,
    hasSuspended,
    hasReason,
    hasApprove,
    sample: text.slice(0, 800),
  };
})()"""


def _deny_stale_e2e_hardened_approvals(api_url: str) -> None:
    listed = http_json("GET", f"{api_url}/api/v1/approvals?limit=100&offset=0")
    if not isinstance(listed, dict):
        return
    approvals = listed.get("approvals")
    if not isinstance(approvals, list):
        return
    stale_ids = [
        str(item.get("id") or "")
        for item in approvals
        if isinstance(item, dict)
        and str(item.get("chat_id") or "").startswith("e2ehardened")
        and str(item.get("id") or "")
    ]
    if not stale_ids:
        return
    http_json(
        "POST",
        f"{api_url}/api/v1/approvals/batch-resolve",
        {"approval_ids": stale_ids, "decision": "reject"},
    )


def _seed_hardened_approval(api_url: str, variant: str) -> dict[str, str]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/approvals/test/seed-hardened-mock?variant={variant}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    approval_id = str(seeded.get("approval_id") or "")
    push_url = str(seeded.get("push_url") or "")
    assert len(chat_id) >= 8
    assert approval_id
    assert push_url.startswith(f"/{chat_id}?approval={approval_id}")
    return {
        "chat_id": chat_id,
        "approval_id": approval_id,
        "push_url": push_url,
    }


def _cleanup_approval(api_url: str, approval_id: str) -> None:
    http_json(
        "POST",
        f"{api_url}/api/v1/approvals/{approval_id}/resolve",
        {"decision": "deny"},
        expected_statuses=frozenset({200, 201, 204, 404}),
    )


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_socially_irreversible_action_renders_banner_and_hides_allow_always() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    _deny_stale_e2e_hardened_approvals(api_url)
    seed = _seed_hardened_approval(api_url, variant="socially_irreversible")
    push_path = seed["push_url"]
    approval_id = seed["approval_id"]
    deeplink_url = f"{ui_url}{push_path}"

    try:
        with open_mcp_page(deeplink_url, timeout_ms=90_000) as (client, page):
            wait_for_state(
                client,
                page,
                "(() => ({ ready: !!document.querySelector('[role=\"dialog\"]') }))()",
                timeout_sec=45.0,
            )
            state = wait_for_state(client, page, _IRREVERSIBLE_BANNER_STATE, timeout_sec=45.0)
            assert state.get("ready") is True, f"Banner not ready: {state}"
            assert state.get("hasBanner") is True
            assert state.get("hasApprove") is True
            # Crucial security invariant: Allow Always must be hidden for socially irreversible actions!
            assert state.get("hasAlwaysAllow") is False, f"Allow always MUST be hidden, but found: {state}"
    finally:
        _cleanup_approval(api_url, approval_id)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_auto_mode_suspended_renders_red_banner_with_consecutive_reason() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    _deny_stale_e2e_hardened_approvals(api_url)
    seed = _seed_hardened_approval(api_url, variant="auto_mode_suspended")
    push_path = seed["push_url"]
    approval_id = seed["approval_id"]
    deeplink_url = f"{ui_url}{push_path}"

    try:
        with open_mcp_page(deeplink_url, timeout_ms=90_000) as (client, page):
            wait_for_state(
                client,
                page,
                "(() => ({ ready: !!document.querySelector('[role=\"dialog\"]') }))()",
                timeout_sec=45.0,
            )
            state = wait_for_state(client, page, _SUSPENDED_BANNER_STATE, timeout_sec=45.0)
            assert state.get("ready") is True, f"Suspended banner not ready: {state}"
            assert state.get("hasSuspended") is True
            assert state.get("hasReason") is True
    finally:
        _cleanup_approval(api_url, approval_id)
