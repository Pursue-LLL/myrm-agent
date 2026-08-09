"""Chrome MCP E2E: failed-bash dual evicted streams → both LiveTerminal Drawers.

Seeds a failed bash step whose stdout AND stderr were evicted. Verifies the
LiveTerminal renders two independent "view full output" entry points (blue for
stdout, amber for stderr) and each drawer reads back its own evicted file.
"""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.evicted_drawer_selectors import (
    CLEAR_RESOURCE_TIMINGS_JS as _CLEAR_RESOURCE_TIMINGS_JS,
)
from tests.support.evicted_drawer_selectors import (
    EXPAND_PROGRESS_PANEL_JS as _EXPAND_PROGRESS_PANEL_JS,
)
from tests.support.evicted_drawer_selectors import (
    TERMINAL_PREVIEW_JS as _TERMINAL_PREVIEW_JS,
)
from tests.support.evicted_drawer_selectors import (
    WAIT_PROGRESS_UI_DOM_JS as _WAIT_PROGRESS_UI_DOM_JS,
)
from tests.support.evicted_drawer_selectors import (
    drawer_ready_js,
)

_FIXTURE_ANSWER = "UECD evicted output E2E fixture answer."
_PAGE_TIMEOUT_MS = 180_000

_PROGRESS_STEPS_READY_JS = f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  if (!msg) return {{ ready: false, count: store?.messages?.length ?? 0 }};
  const metaSteps = Array.isArray(msg.metadata?.progressSteps) ? msg.metadata.progressSteps : [];
  const steps = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
  const step = steps.find((s) => s.evicted_file_ref);
  return {{
    ready: !!step?.evicted_file_ref && !!step?.evicted_stderr_file_ref,
    stdoutRef: step?.evicted_file_ref || null,
    stderrRef: step?.evicted_stderr_file_ref || null,
  }};
}})()"""

CLICK_STDOUT_JS = """(() => {
  const btn = document.querySelector('[data-testid="evicted-view-full-output"]');
  if (!(btn instanceof HTMLElement)) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""

CLICK_STDERR_JS = """(() => {
  const btn = document.querySelector('[data-testid="evicted-view-full-stderr-output"]');
  if (!(btn instanceof HTMLElement)) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""

CLOSE_DRAWER_JS = """(() => {
  const drawer = document.querySelector('[data-testid="evicted-output-drawer"]');
  if (drawer) {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  }
  return { ready: true, dispatched: true };
})()"""

DRAWER_GONE_JS = """(() => ({
  ready: !document.querySelector('[data-testid="evicted-output-drawer"]'),
}))()"""


def _seed_fixture(api_base: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_base}/api/v1/chats/test/seed-evicted-live-terminal-fixture?variant=bash_failure",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2euecd")
    return seeded


def _wait_fixture_assistant_via_api(
    api_base: str, chat_id: str, *, timeout_sec: float = 60.0
) -> None:
    deadline = time.monotonic() + timeout_sec
    last_count = 0
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_base}/api/v1/chats/{chat_id}/messages")
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                messages = data.get("messages")
                if isinstance(messages, list):
                    last_count = len(messages)
                    assistant = next(
                        (
                            item
                            for item in messages
                            if item.get("role") == "assistant"
                            and _FIXTURE_ANSWER in str(item.get("content") or "")
                        ),
                        None,
                    )
                    if assistant is not None:
                        meta = (
                            assistant.get("metadata")
                            if isinstance(assistant.get("metadata"), dict)
                            else {}
                        )
                        steps = meta.get("progressSteps")
                        if (
                            isinstance(steps, list)
                            and steps
                            and any(
                                isinstance(step, dict)
                                and step.get("evicted_file_ref")
                                and step.get("evicted_stderr_file_ref")
                                for step in steps
                            )
                        ):
                            return
        time.sleep(0.5)
    raise AssertionError(
        f"Fixture assistant not ready via API for chat {chat_id} after {timeout_sec:.0f}s "
        f"(last_message_count={last_count})"
    )


def _assert_drawer_reads(client: ChromeMcpClient, page: McpPage, marker: str) -> None:
    drawer = wait_for_state(client, page, drawer_ready_js(marker), timeout_sec=45.0)
    assert drawer.get("ready") is True, json.dumps(drawer, ensure_ascii=False)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(360)
def test_failed_bash_dual_evicted_drawers_read_stdout_and_stderr() -> None:
    """Failed bash: both evicted streams surface their own drawer."""
    api_base = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    seeded = _seed_fixture(api_base)
    print(f"SEED_RESPONSE={json.dumps(seeded, ensure_ascii=False)}")
    chat_id = str(seeded["chat_id"])
    marker_stdout = str(seeded["marker_line"])
    marker_stderr = str(seeded["marker_stderr_line"])
    assert marker_stdout and marker_stderr
    _wait_fixture_assistant_via_api(api_base, chat_id)

    prepare_e2e_ui_session(api_base)
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=_PAGE_TIMEOUT_MS) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        try:
            loaded = wait_for_state(
                client, page, _PROGRESS_STEPS_READY_JS, timeout_sec=120.0
            )
        except AssertionError:
            try:
                diag = client.evaluate(
                    page,
                    """(() => ({
                      body: (document.body?.innerText || '').slice(0, 1600),
                      hasStore: !!window.__myrmChatStore,
                      storeMsgs: (window.__myrmChatStore?.getState?.()?.messages || []).length,
                      apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
                      href: location.href,
                    }))()""",
                    timeout_sec=10.0,
                )
                print(f"PAGE_DIAG={json.dumps(diag, ensure_ascii=False)}")
            except Exception as diag_exc:  # noqa: BLE001 - diagnostic only
                print(f"PAGE_DIAG_FAILED={diag_exc!r}")
            raise
        assert loaded.get("ready") is True, json.dumps(loaded, ensure_ascii=False)

        dom_ready = wait_for_state(client, page, _WAIT_PROGRESS_UI_DOM_JS, timeout_sec=90.0)
        assert dom_ready.get("ready") is True, json.dumps(dom_ready, ensure_ascii=False)

        expanded = wait_for_state(client, page, _EXPAND_PROGRESS_PANEL_JS, timeout_sec=30.0)
        assert expanded.get("ready") is True, json.dumps(expanded, ensure_ascii=False)

        terminal = wait_for_state(client, page, _TERMINAL_PREVIEW_JS, timeout_sec=60.0)
        assert terminal.get("ready") is True, json.dumps(terminal, ensure_ascii=False)
        clear_result = client.evaluate(page, _CLEAR_RESOURCE_TIMINGS_JS, timeout_sec=5.0)
        assert (
            isinstance(clear_result, dict) and clear_result.get("ready") is True
        ), clear_result

        clicked = wait_for_state(client, page, CLICK_STDOUT_JS, timeout_sec=60.0)
        assert clicked.get("clicked") is True, json.dumps(clicked, ensure_ascii=False)
        _assert_drawer_reads(client, page, marker_stdout)

        closed = wait_for_state(client, page, CLOSE_DRAWER_JS, timeout_sec=30.0)
        assert closed.get("dispatched") is True, json.dumps(closed, ensure_ascii=False)
        gone = wait_for_state(client, page, DRAWER_GONE_JS, timeout_sec=30.0)
        assert gone.get("ready") is True, json.dumps(gone, ensure_ascii=False)

        stderr_clicked = wait_for_state(client, page, CLICK_STDERR_JS, timeout_sec=60.0)
        assert stderr_clicked.get("clicked") is True, json.dumps(
            stderr_clicked, ensure_ascii=False
        )
        _assert_drawer_reads(client, page, marker_stderr)
