"""The tool-approval card of a HITL-parked live turn, as the user meets it in the WebUI.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: CDP page helpers)
- tests.support.chrome_skill_hooks_composer (POS: the page's own account of a turn)
- tests.support.chrome_skill_hooks_live_e2e (POS: SkillChat probe)
- tests.support.chrome_skill_hooks_observe (POS: stored chat, backend log)

[OUTPUT]
- wait_for_approval_card() / click_approve(): the tool-approval card of a HITL-parked run
- approve_cards_until_reply(): approve every card the run parks behind until its reply is stored
- describe_unanswered_resume(): failure text for an approved run that never answered

[POS]
Shared by tests/e2e/test_skill_hooks_live_chrome_e2e.py. Like the composer module, nothing here talks to the product
API to approve: the real Approve button is pressed, so the resume request is the one the UI builds.
"""

from __future__ import annotations

import time

from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, get_e2e_api_url, wait_for_state
from tests.support.chrome_skill_hooks_composer import describe_page
from tests.support.chrome_skill_hooks_live_e2e import SkillChat
from tests.support.chrome_skill_hooks_observe import (
    backend_log_since,
    reply_ending_with,
    stored_messages,
    wait_assistant_reply_ending_with,
)

_APPROVAL_VISIBLE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.toolApprovalSnapshot?.() ?? {};
  const queueLen = Number(snap.queueLen ?? 0);
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasApprove = buttons.some((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  const text = document.body?.innerText || '';
  return { ready: hasApprove && queueLen > 0, queueLen, hasApprove, sample: text.slice(0, 600) };
})()"""

_CLICK_APPROVE_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const approve = buttons.find((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  if (!approve) return { ok: false, err: 'approve-button-not-found' };
  approve.scrollIntoView({ block: 'center' });
  approve.click();
  return { ok: true, label: (approve.textContent || '').trim() };
})()"""

# Cards a single turn may ask the user to approve: the model's first command and a retry or two of it.
_APPROVAL_CLICK_BUDGET = 3


def wait_for_approval_card(client: ChromeMcpClient, page: McpPage, *, timeout_sec: float = 240.0) -> dict[str, object]:
    """Block until the tool-approval card is on screen (the run is parked at its HITL interrupt)."""
    return wait_for_state(client, page, _APPROVAL_VISIBLE_JS, timeout_sec=timeout_sec)


def click_approve(client: ChromeMcpClient, page: McpPage) -> None:
    """Press Approve on the tool-approval card, as the user would."""
    clicked = client.evaluate(page, _CLICK_APPROVE_JS, timeout_sec=15.0)
    assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked


def _wait_until_card_consumed(client: ChromeMcpClient, page: McpPage, *, timeout_sec: float) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        card = client.evaluate(page, _APPROVAL_VISIBLE_JS, timeout_sec=15.0)
        if isinstance(card, dict) and card.get("ready") is not True:
            return True
        time.sleep(1.0)
    return False


def approve_cards_until_reply(
    client: ChromeMcpClient, page: McpPage, probe: SkillChat, token: str, *, timeout_sec: float = 240.0
) -> str:
    """Approve every tool-approval card the run parks behind until the reply ending with ``token`` is stored.

    A model that retries a command the executor refused (for instance one chained with ``;``) parks behind a new
    card, and a user approves that one too. Each click is logged, so a turn that needed more than one is visible.
    """
    api_url = get_e2e_api_url()
    deadline = time.monotonic() + timeout_sec
    clicks = 0
    while time.monotonic() < deadline:
        reply = reply_ending_with(stored_messages(probe.chat_id, api_url), token)
        if reply is not None:
            print(f"E2E_ASSISTANT_REPLY[{probe.chat_id}] after {clicks} approval click(s): {reply[:400]}", flush=True)
            return reply
        card = client.evaluate(page, _APPROVAL_VISIBLE_JS, timeout_sec=15.0)
        if isinstance(card, dict) and card.get("ready") is True and clicks < _APPROVAL_CLICK_BUDGET:
            clicks += 1
            print(f"E2E_APPROVE_CLICK: n={clicks} page={str(card.get('sample'))[:200]!r}", flush=True)
            click_approve(client, page)
            _wait_until_card_consumed(client, page, timeout_sec=60.0)
            continue
        time.sleep(2.0)
    return wait_assistant_reply_ending_with(probe.chat_id, api_url, token, timeout_sec=1.0)


def describe_unanswered_resume(
    failure: BaseException,
    client: ChromeMcpClient,
    page: McpPage,
    probe: SkillChat,
    *,
    log_offset: int,
) -> str:
    """Failure text for an approved run that never answered: the hooks' files, the page's view, the server's log."""
    session = probe.out / "session_payload.json"
    session_text = session.read_text(encoding="utf-8")[:300] if session.exists() else None
    return (
        f"{failure}\n"
        f"hook files after approve: {sorted(path.name for path in probe.out.iterdir())}; session payload: {session_text}\n"
        f"{describe_page(client, page)}\n"
        f"--- backend log since approve ---\n{backend_log_since(get_e2e_api_url(), log_offset)}"
    )
