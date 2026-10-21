"""Chrome MCP E2E: LiveTerminal → EvictedOutputDrawer (UECD web_fetch spill, READ lane)."""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    ensure_chat_route,
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
    DRAWER_MOUNT_WAIT_JS as _DRAWER_MOUNT_WAIT_JS,
)
from tests.support.evicted_drawer_selectors import (
    EXPAND_PROGRESS_PANEL_JS as _EXPAND_PROGRESS_PANEL_JS,
)
from tests.support.evicted_drawer_selectors import (
    TERMINAL_PREVIEW_JS as _TERMINAL_PREVIEW_JS,
)
from tests.support.evicted_drawer_selectors import (
    VIEW_FULL_OUTPUT_JS as _VIEW_FULL_OUTPUT_JS,
)
from tests.support.evicted_drawer_selectors import (
    WAIT_PROGRESS_UI_DOM_JS as _WAIT_PROGRESS_UI_DOM_JS,
)
from tests.support.evicted_drawer_selectors import (
    drawer_expired_js,
    drawer_ready_js,
    evicted_request_probe_js,
)

_FIXTURE_ANSWER = "UECD evicted output E2E fixture answer."
_PAGE_TIMEOUT_MS = 180_000

_PROGRESS_STEPS_READY_JS = f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  const errorOverlay = !!document.querySelector('nextjs-portal, nextjs-error-overlay');
  if (!msg) return {{
    ready: false,
    count: store?.messages?.length ?? 0,
    errorOverlay,
  }};
  const metaSteps = Array.isArray(msg.metadata?.progressSteps) ? msg.metadata.progressSteps : [];
  const steps = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
  const step = steps.find((s) => s.evicted_file_ref);
  return {{
    ready: !!step?.evicted_file_ref,
    ref: step?.evicted_file_ref || null,
    hasStdout: !!step?.stdout,
    errorOverlay,
  }};
}})()"""


def _seed_uecd_fixture(api_base: str, *, variant: str = "full") -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_base}/api/v1/chats/test/seed-evicted-live-terminal-fixture?variant={variant}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2euecd")
    return seeded


def _wait_fixture_assistant_via_api(api_base: str, chat_id: str, *, timeout_sec: float = 60.0) -> None:
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
                            if item.get("role") == "assistant" and _FIXTURE_ANSWER in str(item.get("content") or "")
                        ),
                        None,
                    )
                    if assistant is not None:
                        meta = assistant.get("metadata") if isinstance(assistant.get("metadata"), dict) else {}
                        steps = meta.get("progressSteps")
                        if (
                            isinstance(steps, list)
                            and steps
                            and any(isinstance(step, dict) and step.get("evicted_file_ref") for step in steps)
                        ):
                            return
        time.sleep(0.5)
    raise AssertionError(
        f"Fixture assistant not ready via API for chat {chat_id} after {timeout_sec:.0f}s (last_message_count={last_count})"
    )


def _run_drawer_flow(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    marker_line: str | None,
    expect_expired: bool,
) -> None:
    dismiss_blocking_modals(client, page)
    loaded = wait_for_state(client, page, _PROGRESS_STEPS_READY_JS, timeout_sec=120.0)
    assert loaded.get("ready") is True, json.dumps(loaded, ensure_ascii=False)

    dom_ready = wait_for_state(client, page, _WAIT_PROGRESS_UI_DOM_JS, timeout_sec=90.0)
    assert dom_ready.get("ready") is True, json.dumps(dom_ready, ensure_ascii=False)

    expanded = wait_for_state(client, page, _EXPAND_PROGRESS_PANEL_JS, timeout_sec=30.0)
    assert expanded.get("ready") is True, json.dumps(expanded, ensure_ascii=False)

    if not expect_expired:
        terminal = wait_for_state(client, page, _TERMINAL_PREVIEW_JS, timeout_sec=60.0)
        assert terminal.get("ready") is True, json.dumps(terminal, ensure_ascii=False)
    clear_result = client.evaluate(page, _CLEAR_RESOURCE_TIMINGS_JS, timeout_sec=5.0)
    assert isinstance(clear_result, dict) and clear_result.get("ready") is True, clear_result

    # Pre-register the fetch probe so the click-triggered evicted API request is
    # observed regardless of resource-timing buffer saturation.
    client.evaluate(
        page,
        evicted_request_probe_js(expected_offset=0, expected_limit=500),
        timeout_sec=5.0,
    )

    clicked = wait_for_state(client, page, _VIEW_FULL_OUTPUT_JS, timeout_sec=120.0)
    assert clicked.get("clicked") is True, json.dumps(clicked, ensure_ascii=False)

    mounted = wait_for_state(client, page, _DRAWER_MOUNT_WAIT_JS, timeout_sec=90.0)
    assert mounted.get("ready") is True, json.dumps(mounted, ensure_ascii=False)

    # Diagnostic: capture drawer DOM + probe state right after mount, so a
    # missing fetch can be distinguished from a missing/mis-fired drawer mount.
    diag = client.evaluate(
        page,
        """(() => {
          const drawer = document.querySelector('[data-testid="evicted-output-drawer"]');
          const viewBtns = [...document.querySelectorAll('[data-testid="evicted-view-full-output"]')].length;
          const overlay = document.querySelector('nextjs-portal, nextjs-error-overlay');
          return {
            drawerMounted: !!drawer,
            viewBtnCount: viewBtns,
            overlayPresent: !!overlay,
            probeLen: (window.__myrmEvictedFetchProbe || []).length,
            bodyLen: (document.body?.innerText || '').trim().length,
            pathname: location.pathname,
          };
        })()""",
        timeout_sec=5.0,
    )
    print(f"EVT_DIAG: {json.dumps(diag, ensure_ascii=False)}")
    request_probe = wait_for_state(
        client,
        page,
        evicted_request_probe_js(expected_offset=0, expected_limit=500),
        timeout_sec=60.0,
    )
    assert request_probe.get("hit") is True, json.dumps(request_probe, ensure_ascii=False)
    assert request_probe.get("hasLimitZero") is False, json.dumps(request_probe, ensure_ascii=False)

    if expect_expired:
        drawer = wait_for_state(client, page, drawer_expired_js(), timeout_sec=45.0)
    else:
        assert marker_line is not None
        drawer = wait_for_state(client, page, drawer_ready_js(marker_line), timeout_sec=90.0)
    assert drawer.get("ready") is True, json.dumps(drawer, ensure_ascii=False)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(360)
def test_live_terminal_evicted_drawer_reads_uecd_spill_and_expired() -> None:
    """One SHPOIB backend + one Chrome tab: full spill read, then navigate to expired chat."""
    api_base = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    seed_full = _seed_uecd_fixture(api_base, variant="full")
    chat_full = str(seed_full["chat_id"])
    marker_line = str(seed_full["marker_line"])
    _wait_fixture_assistant_via_api(api_base, chat_full)

    seed_expired = _seed_uecd_fixture(api_base, variant="expired")
    chat_expired = str(seed_expired["chat_id"])
    _wait_fixture_assistant_via_api(api_base, chat_expired)

    prepare_e2e_ui_session(api_base)
    warm_ui_route(f"/{chat_full}")
    warm_ui_route(f"/{chat_expired}")

    with open_mcp_page(f"{ui_url}/{chat_full}", timeout_ms=_PAGE_TIMEOUT_MS) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        ensure_chat_route(
            client,
            page,
            target_url=f"{ui_url}/{chat_full}",
            timeout_ms=_PAGE_TIMEOUT_MS,
        )
        _run_drawer_flow(
            client,
            page,
            marker_line=marker_line,
            expect_expired=False,
        )

        ensure_chat_route(
            client,
            page,
            target_url=f"{ui_url}/{chat_expired}",
            timeout_ms=_PAGE_TIMEOUT_MS,
        )

        _run_drawer_flow(
            client,
            page,
            marker_line=None,
            expect_expired=True,
        )
