"""Chrome E2E: Task Steps rollback restores SKILL.md from a real skill_mutation batch."""

from __future__ import annotations

import json
import time
import urllib.request
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from tests.e2e.test_memory_keyword_recall_live_chrome_e2e import _attach_probe_js
from tests.e2e.test_skill_manage_undo_hint_chrome_e2e import (
    _CLICK_OPEN_STEPS_JS,
    _HINT_READY_JS,
    _ROLLBACK_VISIBLE_JS,
    _STEPS_EXPANDED_JS,
)
from tests.support.chrome_api_queue import wait_for_api_queue_to_drain
from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.chrome_skill_undo_probes import UNDO_STATE_JS

_PAGE_TIMEOUT_MS = 180_000
# On a loaded host the chat's messages take minutes to arrive through the API behind the page's mount fan-out.
_ATTACH_TIMEOUT_SEC = 240.0
_QUIET_API_DEADLINE_SEC = 180.0
_SHOW_ROLLBACK_ATTEMPTS = 3

_OPEN_ROLLBACK_DIALOG_JS = """(() => {
  const button = document.querySelector('[data-testid="skill-manage-rollback-button"]');
  if (!button) return { ok: false, err: 'missing-rollback-button' };
  button.click();
  return { ok: true };
})()"""

_CONFIRM_ROLLBACK_JS = """(() => {
  const confirm = document.querySelector('[data-testid="skill-manage-rollback-confirm"]');
  if (!confirm || confirm.disabled) return { ok: false, err: 'missing-confirm-testid' };
  confirm.click();
  return { ok: true };
})()"""

# The success toast only: the panel's own description and the confirm dialog also say "restore previous content".
_TOAST_SUCCESS_JS = """(() => ({
  ready: /Restored \\d+ skill\\(s\\)|已将\\s*\\d+\\s*个技能恢复/.test(document.body?.innerText || ''),
  sample: (document.body?.innerText || '').slice(0, 500),
}))()"""

_ROLLBACK_DONE_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="skill-manage-rollback-button"]:disabled'),
  doneText: document.querySelector('[data-testid="skill-manage-rollback-button"]')?.textContent?.trim() ?? null,
}))()"""

# Marks the button node and records the rollback request, so a button that is not "done" afterwards can be told
# apart: a request that failed or is still running keeps the node, a re-created chat view replaces it.
_WATCH_ROLLBACK_JS = """(() => {
  const button = document.querySelector('[data-testid="skill-manage-rollback-button"]');
  if (!button) return { ok: false, err: 'no-rollback-button' };
  button.__e2eRollbackNode = true;
  if (window.__MYRM_ROLLBACK_TRACE__) return { ok: true };
  const trace = (window.__MYRM_ROLLBACK_TRACE__ = []);
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (...args) => {
    const url = String(args[0]?.url ?? args[0]);
    if (!/\\/mutations\\/[^/]+\\/rollback/.test(url)) return nativeFetch(...args);
    const record = { url: url.slice(-80), startedAt: Math.round(performance.now()) };
    trace.push(record);
    return nativeFetch(...args).then(
      (response) => {
        record.status = response.status;
        record.endedAt = Math.round(performance.now());
        return response;
      },
      (error) => {
        record.error = String(error).slice(0, 160);
        record.endedAt = Math.round(performance.now());
        throw error;
      },
    );
  };
  return { ok: true };
})()"""

_ROLLBACK_DIAGNOSTICS_JS = """(() => {
  const buttons = document.querySelectorAll('[data-testid="skill-manage-rollback-button"]');
  const button = buttons[0];
  return {
    buttonCount: buttons.length,
    hintInDom: Boolean(document.querySelector('[data-testid="skill-manage-undo-hint"]')),
    sameNode: Boolean(button?.__e2eRollbackNode),
    text: button?.textContent?.trim() ?? null,
    disabled: Boolean(button?.disabled),
    stepsExpanded: document.querySelector('[data-testid="progress-steps-toggle"]')?.getAttribute('data-expanded') ?? null,
    timeOrigin: performance.timeOrigin,
    now: Math.round(performance.now()),
    trace: window.__MYRM_ROLLBACK_TRACE__ ?? null,
    toasts: Array.from(document.querySelectorAll('[data-sonner-toast]')).map((node) => (node.textContent ?? '').slice(0, 160)),
  };
})()"""


def _probe_for_report(client: ChromeMcpClient, page: McpPage, js: str) -> str:
    """One page probe for a failure report; a page that cannot be evaluated must not hide the failure being reported."""
    try:
        return json.dumps(client.evaluate(page, js, timeout_sec=15.0), ensure_ascii=False)
    except (RuntimeError, TimeoutError, OSError) as failure:
        return f"unavailable ({failure})"


def describe_chat_page(client: ChromeMcpClient, page: McpPage) -> str:
    """What the page holds for the chat now (the page is gone at teardown): its store, and the undo controls' DOM."""
    return (
        f"chat store: {_probe_for_report(client, page, UNDO_STATE_JS)}\n"
        f"undo controls: {_probe_for_report(client, page, _ROLLBACK_DIAGNOSTICS_JS)}"
    )


def wait_until_api_is_quiet(client: ChromeMcpClient, page: McpPage, api_url: str, *, stage: str) -> None:
    """Act after the page's mount fan-out settled, as a user does.

    On a loaded host the fan-out keeps a request made now queued past the app's 30 s fetch timeout: a mutation clicked
    inside that window is aborted before it is sent, and a chat asked for again inside it only lengthens the queue.
    """
    queue = wait_for_api_queue_to_drain(
        lambda js: client.evaluate(page, js, timeout_sec=60.0, await_promise=True),
        api_url,
        deadline_sec=_QUIET_API_DEADLINE_SEC,
    )
    print(f"E2E_API_QUEUE_GATE: stage={stage} {queue}", flush=True)
    assert queue["outcome"] == "drained", queue


def wait_for_ui(
    client: ChromeMcpClient,
    page: McpPage,
    js: str,
    *,
    timeout_sec: float,
    chat_url: str,
    what: str,
    describe: Callable[[], str],
) -> None:
    """Wait for a UI state; a miss reports what ``describe`` finds in the page, since the page is gone at teardown."""
    try:
        state = wait_for_state(client, page, js, timeout_sec=timeout_sec, page_url=chat_url)
    except AssertionError as failure:
        pytest.fail(f"{what}: {failure}\n{describe()}")
    assert state.get("ready") is True, f"{what}: {state}\n{describe()}"


def show_rollback_button(client: ChromeMcpClient, page: McpPage, chat_url: str, *, describe: Callable[[], str]) -> None:
    """Press the undo hint until Task Steps shows the skill step's Undo button.

    The dev UI is shared and hot-reloads: a file saved by someone else remounts the chat view, which folds Task Steps
    again while the hint stays. A user presses the hint again (it only ever opens Task Steps); so does the test, and
    every repeat is printed.
    """
    for attempt in range(1, _SHOW_ROLLBACK_ATTEMPTS + 1):
        wait_for_ui(
            client, page, _HINT_READY_JS, timeout_sec=120.0, chat_url=chat_url, what="undo hint did not appear", describe=describe
        )
        pressed = client.evaluate(page, _CLICK_OPEN_STEPS_JS, timeout_sec=10.0)
        if isinstance(pressed, dict) and pressed.get("ok") is True:
            try:
                wait_for_state(client, page, _STEPS_EXPANDED_JS, timeout_sec=15.0, page_url=chat_url)
                shown = wait_for_state(client, page, _ROLLBACK_VISIBLE_JS, timeout_sec=30.0, page_url=chat_url)
            except AssertionError:
                shown = {}
            if shown.get("ready") is True:
                return
        print(f"E2E_UNDO_REOPEN: attempt={attempt}/{_SHOW_ROLLBACK_ATTEMPTS} {describe()}", flush=True)
    pytest.fail(f"rollback button not visible after {_SHOW_ROLLBACK_ATTEMPTS} attempts\n{describe()}")


def confirm_rollback(client: ChromeMcpClient, page: McpPage) -> None:
    """Open the rollback dialog from the Undo button and confirm it, as the user does."""
    opened = client.evaluate(page, _OPEN_ROLLBACK_DIALOG_JS, timeout_sec=10.0)
    assert isinstance(opened, dict) and opened.get("ok") is True, opened
    confirmed = client.evaluate(page, _CONFIRM_ROLLBACK_JS, timeout_sec=15.0)
    assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed


def _fetch_skill_md(api_url: str, skill_id: str) -> str:
    url = f"{api_url}/api/v1/skills/{skill_id}/files/SKILL.md"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        body: bytes = response.read()
    return body.decode("utf-8")


def _seed_mutation_batch(api_url: str) -> dict[str, str]:
    """A real skill whose second version came from a mutation batch, through the test-only seeding route."""
    seed = http_json("POST", f"{api_url}/api/v1/skills/test/seed-skill-manage-mutation-batch")
    assert isinstance(seed, dict), seed
    return {key: str(value) for key, value in seed.items()}


def _finished_steps(prefix: str, count: int) -> list[dict[str, object]]:
    """Steps of a long turn around the skill save; the step tree keys on tool_call_id, so each needs its own."""
    return [{"step_key": "analyzing_query", "tool_call_id": f"{prefix}-{index}"} for index in range(count)]


def _persisted_skill_manage_step(batch_id: str) -> dict[str, object]:
    """The step the server persists after a live skill_manage turn (pinned by test_skill_manage_undo_live_api_e2e)."""
    return {
        "step_key": "skill_manage_tool_tool",
        "tool_call_id": f"call_{uuid.uuid4().hex[:24]}",
        "tool_name": "skill_manage_tool",
        "skill_mutation_batch_id": batch_id,
        "reason": "",
        "items": [{"text": "operations: [{'action': 'save', 'content': '---\\nname: systematic-debugging ..."}],
    }


def _seed_chat_with_batch(api_base: str, batch_id: str, *, steps_before: int = 0, steps_after: int = 0) -> str:
    chat_id = f"e2eundorb_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)
    progress_steps = [
        *_finished_steps("before", steps_before),
        _persisted_skill_manage_step(batch_id),
        *_finished_steps("after", steps_after),
    ]
    messages = [
        {
            "messageId": f"msg-user-{chat_id}",
            "chatId": chat_id,
            "role": "user",
            "content": "Apply skill batch for rollback E2E.",
            "createdAt": now.isoformat(),
        },
        {
            "messageId": f"msg-asst-{chat_id}",
            "chatId": chat_id,
            "role": "assistant",
            "content": "Applied skill changes in a batch.",
            "createdAt": (now + timedelta(seconds=1)).isoformat(),
            "metadata": {"progressSteps": progress_steps},
        },
    ]
    http_json(
        "POST",
        f"{api_base}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "E2E Skill Manage Rollback",
            "action_mode": "agent",
            "is_incognito": False,
            "messages": messages,
        },
    )
    return chat_id


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_skill_manage_undo_rollback_restores_skill_md() -> None:
    """Real batch_snapshots + UI confirm rollback restores pre-mutation SKILL.md."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    seed = _seed_mutation_batch(api_url)
    batch_id, skill_id = seed["batch_id"], seed["skill_id"]
    marker_v1, marker_v2 = seed["marker_v1"], seed["marker_v2"]

    assert marker_v2 in _fetch_skill_md(api_url, skill_id)

    prepare_e2e_ui_session(api_url)
    chat_id = _seed_chat_with_batch(api_url, batch_id)
    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=target_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=120.0, page_url=target_url)
        assert bridge.get("ready") is True, bridge

        wait_until_api_is_quiet(client, page, api_url, stage="before-chat-load")
        attached = wait_for_state(client, page, _attach_probe_js(chat_id), timeout_sec=_ATTACH_TIMEOUT_SEC, page_url=target_url)
        assert attached.get("ready") is True, attached

        wait_until_api_is_quiet(client, page, api_url, stage="before-undo")
        show_rollback_button(client, page, target_url, describe=lambda: describe_chat_page(client, page))
        watched = client.evaluate(page, _WATCH_ROLLBACK_JS, timeout_sec=10.0)
        assert isinstance(watched, dict) and watched.get("ok") is True, watched
        confirm_rollback(client, page)

        try:
            toast_state = wait_for_state(client, page, _TOAST_SUCCESS_JS, timeout_sec=45.0, page_url=target_url)
        except AssertionError as failure:
            pytest.fail(f"{failure}\n{describe_chat_page(client, page)}")
        assert toast_state.get("ready") is True, toast_state

        deadline = time.monotonic() + 90.0
        restored = False
        while time.monotonic() < deadline:
            content = _fetch_skill_md(api_url, skill_id)
            if marker_v1 in content and marker_v2 not in content:
                restored = True
                break
            time.sleep(0.5)
        assert restored, "Rollback did not restore v1 marker on SKILL.md"

        try:
            done_state = wait_for_state(client, page, _ROLLBACK_DONE_JS, timeout_sec=45.0, page_url=target_url)
        except AssertionError as failure:
            pytest.fail(f"{failure}\n{describe_chat_page(client, page)}")
        assert done_state.get("ready") is True, done_state
