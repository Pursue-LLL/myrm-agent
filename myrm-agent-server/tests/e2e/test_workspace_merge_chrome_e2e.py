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
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
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
    "Connection refused",
    "E2E_SHARED_API_UNAVAILABLE",
    "E2E_RUNTIME_BINDING_FAILED",
    "Browser Orchestrator error",
    "MUX_ATTACH_RESTART_BLOCKED_PARALLEL",
    "attach-timeout",
)


def _message_wait_timeout_sec() -> float:
    try:
        from e2e_shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return 180.0
    except ImportError:
        pass
    return 90.0


def _bridge_ready_timeout_sec() -> float:
    return _message_wait_timeout_sec()


def _attach_eval_timeout_sec() -> float:
    return _message_wait_timeout_sec()


def _ensure_shpoib_api_binding(
    client: object,
    page: object,
    api_base: str,
    *,
    timeout_sec: float = 90.0,
) -> None:
    """Inject and wait for SHPOIB API binding on shared :3000 UI."""
    from cdp_chat_support import (  # type: ignore[import-not-found]
        E2E_API_BINDING_PROBE_JS,
        e2e_api_base_inject_js,
        e2e_runtime_binding_source,
        wait_e2e_provider_ready,
    )

    expected = api_base.rstrip("/")
    deadline = time.monotonic() + timeout_sec
    last_probe: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(  # type: ignore[attr-defined]
            page,
            E2E_API_BINDING_PROBE_JS,
            timeout_sec=15.0,
        )
        last_probe = raw if isinstance(raw, dict) else {"value": raw}
        actual = str(last_probe.get("apiBase") or "").rstrip("/")
        if actual == expected:
            return
        try:
            provider_ready = wait_e2e_provider_ready(api_url=expected, timeout_sec=5.0)
        except (OSError, TimeoutError, RuntimeError, ValueError):
            provider_ready = False
        if provider_ready or not actual:
            source = e2e_runtime_binding_source()
            if source:
                client.evaluate(  # type: ignore[attr-defined]
                    page,
                    f"(() => {{{source} return true; }})()",
                    timeout_sec=15.0,
                )
            else:
                client.evaluate(  # type: ignore[attr-defined]
                    page,
                    e2e_api_base_inject_js(expected),
                    timeout_sec=15.0,
                )
        time.sleep(0.5)
    raise AssertionError(
        f"SHPOIB API binding failed: expected {expected!r}, probe={last_probe!r}"
    )


def _attach_chat_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const domDeadline = Date.now() + 30_000;
  while (Date.now() < domDeadline) {{
    if (
      document.querySelector('[data-message-end]')
      || document.querySelector('[data-chat-input]')
    ) {{
      break;
    }}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }}
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ok: snap.chatId === {chat_id_json} && (snap.userCount ?? 0) >= 1,
    hasChatSurface: Boolean(
      document.querySelector('[data-message-end]')
      || document.querySelector('[data-chat-input]'),
    ),
    snap,
  }};
}})()"""


def _merge_store_ready_js() -> str:
    return f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  const failures = Array.isArray(msg?.workspaceMergeFailures)
    ? msg.workspaceMergeFailures
    : [];
  return {{
    ready: failures.length > 0,
    failureCount: failures.length,
    msgCount: store?.messages?.length ?? 0,
  }};
}})()"""


def _chat_surface_ready_js() -> str:
    return """(() => ({
  ready: Boolean(
    document.querySelector('[data-message-end]')
    || document.querySelector('[data-chat-input]'),
  ),
}))()"""


def _assert_merge_panel_ui(
    client: object,
    page: object,
    *,
    chat_id: str,
    page_url: str,
    api_url: str,
) -> None:
    api_base = api_url.rstrip("/")

    bridge_ready = wait_for_react_e2e_bridge(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        timeout_sec=_bridge_ready_timeout_sec(),
        page_url=page_url,
    )
    assert bridge_ready.get("ready") is True, json.dumps(
        bridge_ready,
        ensure_ascii=False,
    )

    _ensure_shpoib_api_binding(
        client,
        page,
        api_base,
        timeout_sec=_attach_eval_timeout_sec(),
    )

    attached = client.evaluate(  # type: ignore[attr-defined]
        page,
        _attach_chat_probe(chat_id),
        timeout_sec=_attach_eval_timeout_sec(),
    )
    assert isinstance(attached, dict) and attached.get("ok") is True, attached
    assert attached.get("hasChatSurface") is True, attached

    dismiss_blocking_modals(client, page)  # type: ignore[arg-type]

    surface_state = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _chat_surface_ready_js(),
        timeout_sec=_attach_eval_timeout_sec(),
    )
    assert surface_state.get("ready") is True, json.dumps(
        surface_state,
        ensure_ascii=False,
    )

    message_ready = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _message_ready_js(),
        timeout_sec=_attach_eval_timeout_sec(),
    )
    assert message_ready.get("ready") is True, json.dumps(
        message_ready,
        ensure_ascii=False,
    )

    store_state = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _merge_store_ready_js(),
        timeout_sec=45.0,
    )
    assert store_state.get("ready") is True, json.dumps(
        store_state,
        ensure_ascii=False,
    )

    def _wait_panel(*, timeout_sec: float) -> dict[str, object]:
        return wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _merge_panel_ready_js(),
            timeout_sec=timeout_sec,
        )

    try:
        panel_state = _wait_panel(timeout_sec=45.0)
    except AssertionError:
        panel_state = {"ready": False}

    if panel_state.get("ready") is not True:
        client.navigate(page, page_url)  # type: ignore[attr-defined]
        time.sleep(2.0)
        dismiss_blocking_modals(client, page)  # type: ignore[arg-type]
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)  # type: ignore[attr-defined]

        bridge_ready = wait_for_react_e2e_bridge(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            timeout_sec=90.0,
            page_url=page_url,
        )
        assert bridge_ready.get("ready") is True, json.dumps(
            bridge_ready,
            ensure_ascii=False,
        )
        _ensure_shpoib_api_binding(
            client,
            page,
            api_base,
            timeout_sec=60.0,
        )
        attached = client.evaluate(  # type: ignore[attr-defined]
            page,
            _attach_chat_probe(chat_id),
            timeout_sec=_attach_eval_timeout_sec(),
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached
        dismiss_blocking_modals(client, page)  # type: ignore[arg-type]
        surface_state = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _chat_surface_ready_js(),
            timeout_sec=60.0,
        )
        assert surface_state.get("ready") is True, json.dumps(
            surface_state,
            ensure_ascii=False,
        )
        panel_state = _wait_panel(timeout_sec=60.0)

    assert panel_state.get("ready") is True, json.dumps(
        panel_state,
        ensure_ascii=False,
    )
    assert panel_state.get("isFallback") is not True, json.dumps(
        panel_state,
        ensure_ascii=False,
    )
    assert panel_state.get("hasChatSurface") is True, json.dumps(
        panel_state,
        ensure_ascii=False,
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


def _force_mux_heal_before_retry() -> None:
    _require_e2e_cdp_ready(budget_sec=45.0)
    try:
        from mux_attach_force_restart import force_mux_attach_restart_scoped

        force_mux_attach_restart_scoped(reason="workspace merge chrome outer retry")
    except RuntimeError as exc:
        if "MUX_ATTACH_RESTART_BLOCKED_PARALLEL" not in str(exc):
            raise
    time.sleep(5.0)


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
  const toggle = panel?.querySelector('button');
  let bodyText = document.body?.innerText || '';
  if (toggle && !/task_index=1/i.test(bodyText)) {{
    toggle.click();
    bodyText = document.body?.innerText || '';
  }}
  const isFallback = Boolean(document.querySelector('[data-e2e-merge-fallback="true"]'));
  const hasChatSurface = Boolean(document.querySelector('[data-message-end]'));
  const storeLoading = Boolean(store?.loading || store?.isStreaming);
  const hasTitle = /Workspace Merge Failed|工作区合并失败|工作區合併失敗/i.test(bodyText);
  const hasError = /task_index=1/i.test(bodyText)
    || failures.some((item) => String(item?.message || '').includes('task_index=1'));
  return {{
    ready:
      failures.length > 0
      && !!panel
      && hasChatSurface
      && !isFallback
      && hasTitle
      && hasError
      && (!storeLoading || !!panel),
    failureCount: failures.length,
    hasPanel: !!panel,
    hasChatSurface,
    hasTitle,
    hasError,
    storeLoading,
    isFallback,
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


def _ensure_merge_metadata_ready(
    api_url: str, chat_id: str, *, timeout_sec: float = 45.0
) -> None:
    """Poll API before Chrome — attach stack may restart backend briefly under parallel mux."""
    deadline = time.monotonic() + timeout_sec
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            payload = http_json(
                "GET",
                f"{api_url}/api/v1/chats/{chat_id}/messages",
            )
            messages: list[object] = []
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, dict) and isinstance(data.get("messages"), list):
                    messages = data["messages"]
                elif isinstance(payload.get("messages"), list):
                    messages = payload["messages"]
            assistant = next(
                (
                    msg
                    for msg in messages
                    if isinstance(msg, dict) and msg.get("role") == "assistant"
                ),
                None,
            )
            if isinstance(assistant, dict):
                metadata = assistant.get("metadata")
                meta = metadata if isinstance(metadata, dict) else {}
                failures = meta.get("workspaceMergeFailures")
                if isinstance(failures, list) and len(failures) >= 1:
                    return
                last_error = f"metadata missing failures: {meta!r}"
            else:
                last_error = f"assistant message missing; count={len(messages)}"
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(0.3)
    raise AssertionError(
        f"workspace merge metadata not ready chat={chat_id}: {last_error}"
    )


def _warm_chat_routes(chat_id: str) -> None:
    warm_ui_route("/")
    warm_ui_route(f"/{chat_id}")


def _run_panel_assertions(
    api_url: str, ui_url: str, *, warm_route: bool = True
) -> None:
    seeded = _seed_workspace_merge_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    _ensure_merge_metadata_ready(api_url, chat_id)
    if warm_route:
        _warm_chat_routes(chat_id)
    target_url = f"{ui_url.rstrip('/')}/{chat_id}"

    with open_mcp_page(target_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        _assert_merge_panel_ui(
            client,
            page,
            chat_id=chat_id,
            page_url=target_url,
            api_url=api_url,
        )


def _run_reload_assertions(
    api_url: str, ui_url: str, *, warm_route: bool = True
) -> None:
    seeded = _seed_workspace_merge_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    _ensure_merge_metadata_ready(api_url, chat_id)
    if warm_route:
        _warm_chat_routes(chat_id)
    target_url = f"{ui_url.rstrip('/')}/{chat_id}"

    with open_mcp_page(target_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        _assert_merge_panel_ui(
            client,
            page,
            chat_id=chat_id,
            page_url=target_url,
            api_url=api_url,
        )

        client.navigate(page, target_url)  # type: ignore[attr-defined]
        time.sleep(2.0)
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        _assert_merge_panel_ui(
            client,
            page,
            chat_id=chat_id,
            page_url=target_url,
            api_url=api_url,
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


def _api_url_for_seed() -> str:
    return get_e2e_api_url()


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD"
, private_reason="exclusive_backend")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_workspace_merge_shows_warning_panel() -> None:
    from e2e_session_lifecycle import complete_bootstrap_phase

    complete_bootstrap_phase(phase_label="test_workspace_merge_shows_warning_panel")
    api_url = _api_url_for_seed()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_panel_assertions, api_url, ui_url)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD"
, private_reason="exclusive_backend")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_workspace_merge_warning_survives_page_reload() -> None:
    """Hydrate from DB: reload must still show WorkspaceMergeWarning from metadata."""
    from e2e_session_lifecycle import complete_bootstrap_phase

    complete_bootstrap_phase(
        phase_label="test_workspace_merge_warning_survives_page_reload"
    )
    api_url = _api_url_for_seed()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_reload_assertions, api_url, ui_url)
