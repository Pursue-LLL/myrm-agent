"""Chrome E2E: workspace merge failure — READ lane WorkspaceMergeWarning + reload hydrate."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_FIXTURE_ANSWER = "Workspace merge E2E fixture answer."
_MAX_ATTEMPTS = 3
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "CDP",
    "Chrome MCP",
    "Browser Orchestrator",
    "No target with given id",
    "connection reset",
    "wait_for_state",
    "Browser state did not become ready",
    "Page shell did not hydrate",
    "E2E_MUX_DAEMONS",
    "muxDaemons",
    "transport dead",
    "transport unavailable",
    "recover_mux_transport",
    "recover_mux",
    "chrome-error",
    "Runtime.evaluate",
    "CDP request timeout",
    "no-bridge",
    "PARENT_LEASE_NOT_ACTIVE",
    "E2E_LEASE_INVALID",
    "LEASE_NOT_ACTIVE",
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_BRIDGE_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  return {
    ready: typeof bridge?.attachToChat === 'function',
    hasBridge: !!bridge,
    hasAttach: typeof bridge?.attachToChat === 'function',
  };
})()"""


def _attach_chat_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ok: snap.chatId === {chat_id_json} && (snap.userCount ?? 0) >= 1,
    snap,
  }};
}})()"""


def _force_mux_heal_before_retry() -> None:
    _require_e2e_cdp_ready(budget_sec=45.0)
    from mux_attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="workspace merge chrome outer retry")
    time.sleep(3.0)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if "E2E_USER_CLOSED_TAB" in text:
        return False
    if "E2E_ORCHESTRATOR_LEASE_DENIED" in text or "LEASE_DENIED" in text:
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _merge_panel_ready_js() -> str:
    return f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  const failures = Array.isArray(msg?.workspaceMergeFailures)
    ? msg.workspaceMergeFailures
    : [];
  const panel = document.querySelector('[data-testid="workspace-merge-warning"]');
  const bodyText = document.body?.innerText || '';
  const hasTitle = /Workspace Merge Failed|工作区合并失败|工作區合併失敗/i.test(bodyText);
  const hasError = /task_index=1/i.test(bodyText)
    || failures.some((item) => String(item?.message || '').includes('task_index=1'));
  return {{
    ready: failures.length > 0 && !!panel && hasTitle && hasError,
    failureCount: failures.length,
    hasPanel: !!panel,
    hasTitle,
    hasError,
    sample: bodyText.slice(0, 500),
  }};
}})()"""


def _message_ready_js() -> str:
    return f"""(() => {{
      const target = {json.dumps(_FIXTURE_ANSWER)};
      const store = window.__myrmChatStore?.getState?.();
      const msg = (store?.messages || []).find(
        (item) => item.role === 'assistant' && (item.content || '').includes(target),
      );
      return {{ ready: !!msg, count: store?.messages?.length ?? 0 }};
    }})()"""


def _seed_workspace_merge_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-workspace-merge-fixture?variant=batch_merge_fail",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    message_id = str(seeded.get("message_id") or "")
    ui_path = str(seeded.get("ui_path") or "")
    assert chat_id.startswith("e2ewsmr")
    assert len(message_id) >= 8
    assert ui_path == f"/{chat_id}"
    return seeded


def _run_panel_assertions(
    api_url: str, ui_url: str, *, warm_route: bool = True
) -> None:
    seeded = _seed_workspace_merge_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    if warm_route:
        warm_ui_route(f"/{chat_id}")

    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        bridge_ready = wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=90.0,
        )
        assert bridge_ready.get("ready") is True, json.dumps(
            bridge_ready,
            ensure_ascii=False,
        )

        attached = client.evaluate(page, _attach_chat_probe(chat_id), timeout_sec=90.0)
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        message_ready = wait_for_state(
            client,
            page,
            _message_ready_js(),
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready,
            ensure_ascii=False,
        )

        dismiss_blocking_modals(client, page)

        panel = wait_for_state(
            client,
            page,
            _merge_panel_ready_js(),
            timeout_sec=30.0,
        )
        assert panel.get("ready") is True, json.dumps(panel, ensure_ascii=False)
        assert int(panel.get("failureCount") or 0) >= 1


def _run_reload_assertions(
    api_url: str, ui_url: str, *, warm_route: bool = True
) -> None:
    seeded = _seed_workspace_merge_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    if warm_route:
        warm_ui_route(f"/{chat_id}")

    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        bridge_ready = wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=90.0,
        )
        assert bridge_ready.get("ready") is True, json.dumps(
            bridge_ready,
            ensure_ascii=False,
        )

        attached = client.evaluate(page, _attach_chat_probe(chat_id), timeout_sec=90.0)
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        message_ready = wait_for_state(
            client,
            page,
            _message_ready_js(),
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready,
            ensure_ascii=False,
        )

        dismiss_blocking_modals(client, page)

        before_reload = wait_for_state(
            client,
            page,
            _merge_panel_ready_js(),
            timeout_sec=30.0,
        )
        assert before_reload.get("ready") is True, json.dumps(
            before_reload,
            ensure_ascii=False,
        )

        reload_mcp_page(client, page)
        dismiss_blocking_modals(client, page)

        after_reload = wait_for_state(
            client,
            page,
            _merge_panel_ready_js(),
            timeout_sec=120.0,
        )
        assert after_reload.get("ready") is True, json.dumps(
            after_reload,
            ensure_ascii=False,
        )


def _run_with_transport_retry(
    runner: Callable[..., None],
    api_url: str,
    ui_url: str,
) -> None:
    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            runner(api_url, ui_url, warm_route=(attempt == 1))
            return
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_workspace_merge_shows_warning_panel() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_panel_assertions, api_url, ui_url)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_workspace_merge_warning_survives_page_reload() -> None:
    """Hydrate from DB: reload must still show WorkspaceMergeWarning from metadata."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_reload_assertions, api_url, ui_url)
