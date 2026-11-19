"""Real Chrome MCP E2E: importing the same rule file twice on the memory page keeps one copy of the rule.

Covers the real-user path of the import button on /settings/memory, with no model involved:
  - The user uploads a native JSON file holding one rule, reviews it in the dialog and confirms
  - The confirm answer the page receives counts the rule and the memory API lists it once
  - The user uploads the same file again and confirms: the page is told 0 memories were imported and the rule is
    still listed once, as the review dialog promises for entries that already exist in memory

The page turns the confirm answer into a toast whose wording depends on the runtime's post-import diagnostics (a
runtime without an embedding provider reports them as critical), so the test reads the answer itself.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)

_MEMORY_API = "/api/v1/memory"
_STORED_WAIT_SEC = 20.0

_IMPORT_INPUT_READY_JS = """(() => {
  const hasInput = !!document.querySelector('input[type="file"][accept*="json"]');
  return { ready: hasInput && (document.body?.innerText || '').length > 0 };
})()"""

# Starts a fresh list of the confirm answers the page receives; the page's fetch is wrapped once.
_RECORD_CONFIRMS_JS = """(() => {
  window.__memoryImportConfirms = [];
  if (window.__memoryImportConfirmWrapped) { return { ok: true }; }
  window.__memoryImportConfirmWrapped = true;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const target = args[0];
    const url = typeof target === 'string' ? target : (target && target.url) || '';
    if (url.includes('/api/v1/memory/import/confirm')) {
      const body = await response.clone().json().catch(() => ({}));
      window.__memoryImportConfirms.push({ status: response.status, totalImported: body.total_imported ?? null });
    }
    return response;
  };
  return { ok: true };
})()"""

_CONFIRM_ANSWERS_JS = """(() => {
  const answers = window.__memoryImportConfirms || [];
  return { ready: answers.length > 0, answers };
})()"""

# The dialog's confirm button reads "Import" (en) / "确认导入" (zh); its title and cancel button never match.
_CONFIRM_BUTTON_JS = """const dialog = document.querySelector('[role="dialog"]');
  const confirm = dialog && Array.from(dialog.querySelectorAll('button')).find(
    (button) => /^(Import|确认导入)$/.test((button.textContent || '').trim()),
  );"""

_REVIEW_READY_JS = (
    "(() => {\n  "
    + _CONFIRM_BUTTON_JS
    + """
  return {
    ready: !!confirm && !confirm.disabled && (dialog.textContent || '').includes(__MARKER__),
    snippet: (dialog?.textContent || '').trim().slice(0, 300),
  };
})()"""
)

_CONFIRM_JS = (
    "(() => {\n  "
    + _CONFIRM_BUTTON_JS
    + """
  if (!confirm || confirm.disabled) { return { clicked: false }; }
  confirm.click();
  return { clicked: true };
})()"""
)

_UPLOAD_JS = """(() => {
  const input = document.querySelector('input[type="file"][accept*="json"]');
  if (!input) { return { ok: false, reason: 'file-input-missing' }; }
  const file = new File([__FILE_TEXT__], 'e2e-rule-reimport.json', { type: 'application/json' });
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true };
})()"""


def _rule_file(marker: str) -> str:
    """A native export holding one rule; the marker keeps the rule apart from whatever the runtime already holds."""
    trigger = f"When the re-import check {marker} runs"
    action = f"Reply with the code word {marker}"
    rule = {"content": f"{trigger}: {action}", "trigger": trigger, "action": action}
    return json.dumps({"version": "1", "data": {"procedural": [rule]}})


def _stored_rules(api_url: str, marker: str) -> list[dict[str, object]]:
    payload = http_json("GET", f"{api_url}{_MEMORY_API}/?type=procedural&page_size=100")
    assert isinstance(payload, dict) and isinstance(payload.get("items"), list), payload
    return [item for item in payload["items"] if isinstance(item, dict) and marker in json.dumps(item, ensure_ascii=False)]


def _wait_for_stored_count(api_url: str, marker: str, expected: int) -> None:
    deadline = time.monotonic() + _STORED_WAIT_SEC
    rules = _stored_rules(api_url, marker)
    while len(rules) != expected and time.monotonic() < deadline:
        time.sleep(0.5)
        rules = _stored_rules(api_url, marker)
    assert len(rules) == expected, f"expected {expected} stored rule(s) for {marker}, found {rules}"


def _import_through_dialog(client: ChromeMcpClient, page: McpPage, page_url: str, marker: str) -> int:
    """Pick the rule file, confirm it in the review dialog and return how many memories the page was told it imported."""
    client.evaluate(page, _RECORD_CONFIRMS_JS, timeout_sec=10.0)
    upload = client.evaluate(
        page,
        _UPLOAD_JS.replace("__FILE_TEXT__", json.dumps(_rule_file(marker))),
        timeout_sec=20.0,
    )
    assert isinstance(upload, dict) and upload.get("ok") is True, f"upload failed: {upload!r}"

    review = wait_for_state(
        client,
        page,
        _REVIEW_READY_JS.replace("__MARKER__", json.dumps(marker)),
        timeout_sec=60.0,
        page_url=page_url,
        blank_heal_mode="direct",
    )
    assert review.get("ready") is True, f"review dialog not ready: {review!r}"

    confirmed = client.evaluate(page, _CONFIRM_JS, timeout_sec=10.0)
    assert isinstance(confirmed, dict) and confirmed.get("clicked") is True, f"confirm not clicked: {confirmed!r}"

    answered = wait_for_state(
        client,
        page,
        _CONFIRM_ANSWERS_JS,
        timeout_sec=60.0,
        page_url=page_url,
        blank_heal_mode="direct",
    )
    answers = answered.get("answers")
    assert isinstance(answers, list) and len(answers) == 1, f"expected one confirm answer, got {answered!r}"
    answer = answers[0]
    assert isinstance(answer, dict) and answer.get("status") == 200, f"import was not accepted: {answer!r}"
    total = answer.get("totalImported")
    assert isinstance(total, int), f"confirm answer carries no import count: {answer!r}"
    return total


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_memory_rule_reimport_keeps_one_copy_chrome_e2e() -> None:
    """The same rule file imported twice through the memory page leaves one stored copy of the rule."""
    api_url = get_e2e_api_url()
    page_url = f"{get_e2e_ui_url().rstrip('/')}/settings/memory"
    marker = f"reimport-{uuid.uuid4().hex[:8]}"
    prepare_e2e_ui_session(api_url)

    try:
        with open_settings_subroute("/settings/memory", layout_timeout_sec=120.0) as (client, page):
            dismiss_blocking_modals(client, page)
            ready = wait_for_state(
                client,
                page,
                _IMPORT_INPUT_READY_JS,
                timeout_sec=90.0,
                page_url=page_url,
                blank_heal_mode="direct",
            )
            assert ready.get("ready") is True, f"memory page not ready: {ready!r}"

            first = _import_through_dialog(client, page, page_url, marker)
            assert first == 1, f"the first import should store the rule, the page was told {first} were imported"
            _wait_for_stored_count(api_url, marker, expected=1)

            second = _import_through_dialog(client, page, page_url, marker)
            assert second == 0, f"the same file again should add nothing, the page was told {second} were imported"
            _wait_for_stored_count(api_url, marker, expected=1)
    finally:
        for rule in _stored_rules(api_url, marker):
            http_json("DELETE", f"{api_url}{_MEMORY_API}/{rule['id']}?memory_type=procedural")
