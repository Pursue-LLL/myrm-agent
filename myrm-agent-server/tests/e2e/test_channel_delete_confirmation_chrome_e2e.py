"""Chrome MCP E2E: channel instance delete confirmation flows.

Covers the real-browser wiring behind the settings "delete instance" confirmation
dialog (``ConfirmDialog``) for WeChat multi-account:

- Primary account logout confirmation: open the delete dialog on the primary
  WeChat card, cancel keeps the account, confirm triggers the real
  ``POST /wechat-logout`` and closes the dialog.
- Extra instance delete confirmation: seed a WeChat extra instance through the
  real ``POST /instances`` API, delete it through the UI confirmation dialog,
  and verify the card disappears from the settings page and from the backend.
- Delete failure resilience: after the dialog is open, the instance is removed
  out-of-band (concurrent deletion), so the UI confirm hits a backend 404; the
  dialog must stay open (error toast shown) instead of closing, and the user
  can cancel afterwards.

All flows drive the real WebUI (settings → channels → WeChat) via Chrome MCP
and assert on real API effects (logout / instance removal / 404-on-missing).

Execution mode is PRIVATE because the flows depend on the workspace backend
code (WeChat channel registered as enabled by default; ``list_channel_instances``
exposing bare instance ids that the delete API accepts). The shared :8080 epoch
may run older code where the primary WeChat channel is persisted as ``disabled``
(hiding its config panel by design), which would make the flow untestable there.

Each flow still ensures the primary channel is enabled via the real toggle API
as a robustness guard, and restores the previous state afterwards.
"""

from __future__ import annotations

import json
import sys

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)

_CHANNELS_PATH = "/settings/channels"
_INSTANCES_ENDPOINT = "/api/v1/channels/manage/instances"

# Navigate to settings → channels and select the WeChat channel card.
_NAV_TO_WECHAT_JS = """(() => {
  try {
    window.resizeTo(1280, 900);
  } catch {
    // ignore
  }
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
    localStorage.setItem('myrm-selected-channel', 'wechat');
  } catch {
    // ignore
  }
  if (!location.pathname.includes('/settings/channels')) {
    location.href = '/settings/channels';
    return { ready: false, navigating: true, pathname: location.pathname };
  }
  const item = document.querySelector('[data-testid="channel-list-item-wechat"]');
  if (item) {
    item.click();
  }
  const delBtn = document.querySelector('[aria-label="delete-wechat"]');
  const body = document.body.innerText || '';
  return {
    ready: !!delBtn,
    hasDeleteBtn: !!delBtn,
    hasCard: !!item,
    hasAuthToken: !!localStorage.getItem('auth_token'),
    width: window.innerWidth,
    bodyLen: body.length,
    hasNoChannel: body.includes('wechatNoChannel'),
    bodySnippet: body.slice(0, 800),
  };
})()"""

# Navigate to settings → channels and select the Feishu channel card.
def _nav_to_channel_js(channel_type: str) -> str:
    """Navigate to settings → channels and select the requested channel card.

    Reuses the same UX path as ``_NAV_TO_WECHAT_JS`` but parameterized by the
    channel card test id and primary delete-button ``aria-label``.
    """
    return f"""(() => {{
  try {{
    window.resizeTo(1280, 900);
  }} catch {{
    // ignore
  }}
  try {{
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
    localStorage.setItem('myrm-selected-channel', '{channel_type}');
  }} catch {{
    // ignore
  }}
  if (!location.pathname.includes('/settings/channels')) {{
    location.href = '/settings/channels';
    return {{ ready: false, navigating: true, pathname: location.pathname }};
  }}
  const item = document.querySelector('[data-testid="channel-list-item-{channel_type}"]');
  if (item) {{
    item.click();
  }}
  const delBtn = document.querySelector('[aria-label="delete-{channel_type}"]');
  const body = document.body.innerText || '';
  return {{
    ready: !!delBtn,
    hasDeleteBtn: !!delBtn,
    hasCard: !!item,
    hasAuthToken: !!localStorage.getItem('auth_token'),
    width: window.innerWidth,
    bodyLen: body.length,
    hasNoChannel: body.includes('{channel_type}NoChannel'),
    bodySnippet: body.slice(0, 800),
  }};
}})()"""


_NAV_TO_FEISHU_JS = _nav_to_channel_js("feishu")


# Click the primary card delete button to open the confirmation dialog.
_OPEN_DELETE_DIALOG_JS = """(() => {
  const delBtn = document.querySelector('[aria-label="delete-wechat"]');
  if (!delBtn) {
    return { ok: false, err: 'delete-btn-not-found' };
  }
  delBtn.click();
  return { ok: true };
})()"""

# Report whether the confirmation dialog is currently open (by its buttons).
_DIALOG_OPEN_STATE_JS = """(() => {
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  const cancel = document.querySelector('[data-testid="confirm-dialog-cancel"]');
  return {
    ready: !!confirm && !!cancel,
    hasConfirm: !!confirm,
    hasCancel: !!cancel,
    bodyLen: (document.body?.innerText || '').length,
    bodySnippet: (document.body.innerText || '').slice(0, 300),
  };
})()"""

# The dialog is open AND the in-flight confirm request has settled, i.e. both
# buttons are clickable again. ConfirmDialog keeps the dialog open on failure
# and only releases isLoading in the finally block; clicking Cancel while the
# button is disabled is a no-op, which is what Flow 3 must avoid.
_DIALOG_STAYS_OPEN_JS = """(() => {
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  const cancel = document.querySelector('[data-testid="confirm-dialog-cancel"]');
  return {
    ready: !!confirm && !!cancel && !confirm.disabled && !cancel.disabled,
    hasConfirm: !!confirm,
    hasCancel: !!cancel,
    confirmDisabled: confirm ? confirm.disabled : null,
    cancelDisabled: cancel ? cancel.disabled : null,
    bodyLen: (document.body?.innerText || '').length,
    bodySnippet: (document.body.innerText || '').slice(0, 300),
  };
})()"""

# Cancel keeps the account: the dialog closes and the delete button remains.
_DIALOG_CLOSED_KEEPING_JS = """(() => {
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  const delBtn = document.querySelector('[aria-label="delete-wechat"]');
  return {
    ready: !confirm && !!delBtn,
    dialogClosed: !confirm,
    hasDeleteBtn: !!delBtn,
    bodyLen: (document.body?.innerText || '').length,
  };
})()"""

# Confirm triggers logout and the dialog closes after the API round-trip.
_DIALOG_CLOSED_AFTER_CONFIRM_JS = """(() => {
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  return {
    ready: !confirm,
    dialogClosed: !confirm,
    bodyLen: (document.body?.innerText || '').length,
    bodySnippet: (document.body.innerText || '').slice(0, 300),
  };
})()"""

_CANCEL_DIALOG_JS = """(() => {
  const cancel = document.querySelector('[data-testid="confirm-dialog-cancel"]');
  if (!cancel) return { ok: false, err: 'cancel-not-found' };
  if (cancel.disabled) return { ok: false, err: 'cancel-disabled' };
  cancel.click();
  return { ok: true };
})()"""

_CONFIRM_DIALOG_JS = """(() => {
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  if (!confirm) return { ok: false, err: 'confirm-not-found' };
  confirm.click();
  return { ok: true };
})()"""


def _extra_instance_probe_js(instance_id: str, channel_type: str = "wechat") -> str:
    """Return a probe that detects the extra-instance card delete button."""
    return f"""(() => {{
  const delBtn = document.querySelector('[aria-label="delete-{channel_type}_{instance_id}"]');
  return {{
    ready: !!delBtn,
    hasDeleteBtn: !!delBtn,
    bodyLen: (document.body?.innerText || '').length,
    bodySnippet: (document.body.innerText || '').slice(0, 300),
  }};
}})()"""


def _extra_instance_open_js(instance_id: str, channel_type: str = "wechat") -> str:
    """Return a probe that clicks the extra-instance card delete button.

    Desktop mounts the config card twice (right-hand panel + in-list detail).
    We click the LAST matching button — the visible right-hand panel one — to
    drive the real user path. Both cards share one store, so the dialog belongs
    to the visible card.
    """
    return f"""(() => {{
  const btns = document.querySelectorAll('[aria-label="delete-{channel_type}_{instance_id}"]');
  if (btns.length === 0) return {{ ok: false, err: 'delete-btn-not-found' }};
  const delBtn = btns[btns.length - 1];
  delBtn.click();
  return {{ ok: true, count: btns.length }};
}})()"""


def _extra_instance_gone_js(instance_id: str, channel_type: str = "wechat") -> str:
    """Return a probe that confirms the extra-instance card is gone.

    Also reports whether the confirm dialog is still open so a timeout can be
    attributed to a failed DELETE (dialog stays open, by design) versus a
    successful DELETE that the UI failed to re-render (dialog closed).
    """
    return f"""(() => {{
  const delBtn = document.querySelector('[aria-label="delete-{channel_type}_{instance_id}"]');
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  const cancel = document.querySelector('[data-testid="confirm-dialog-cancel"]');
  return {{
    ready: !delBtn,
    instanceGone: !delBtn,
    dialogOpen: !!confirm && !!cancel,
    hasDeleteBtn: !!delBtn,
    bodyLen: (document.body?.innerText || '').length,
  }};
}})()"""


def _extra_instance_dialog_closed_js(instance_id: str, channel_type: str = "wechat") -> str:
    """Probe: the confirm dialog is closed but the (stale) extra-instance card remains."""
    return f"""(() => {{
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  const delBtn = document.querySelector('[aria-label="delete-{channel_type}_{instance_id}"]');
  const primaryBtn = document.querySelector('[aria-label="delete-{channel_type}"]');
  return {{
    ready: !confirm && !!delBtn,
    dialogClosed: !confirm,
    hasDeleteBtn: !!delBtn,
    hasPrimaryBtn: !!primaryBtn,
    bodyLen: (document.body?.innerText || '').length,
    bodyFull: (document.body.innerText || '').slice(0, 2000),
    navType: performance.getEntriesByType('navigation')[0]?.type || 'navigate',
    href: location.href,
  }};
}})()"""


def _status_diagnostics(api_url: str) -> dict[str, object]:
    """Best-effort backend status snapshot to pinpoint why the UI may not render the delete button."""
    diag: dict[str, object] = {}
    try:
        statuses = http_json("GET", f"{api_url}/api/v1/channels/manage/status")
        if isinstance(statuses, list):
            diag["statusCount"] = len(statuses)
            diag["statusNames"] = [s.get("name") for s in statuses if isinstance(s, dict)]
            wechat = next((s for s in statuses if isinstance(s, dict) and s.get("name") == "wechat"), None)
            diag["wechatStatus"] = wechat
        else:
            diag["statusRaw"] = statuses
    except RuntimeError as exc:
        diag["statusErr"] = str(exc)[:400]
    try:
        wechat_status = http_json("GET", f"{api_url}/api/v1/channels/manage/wechat/status")
        diag["wechatEndpoint"] = wechat_status
    except RuntimeError as exc:
        diag["wechatEndpointErr"] = str(exc)[:400]
    return diag


def _wechat_toggle(api_url: str, enabled: bool) -> None:
    """Enable/disable the primary WeChat channel via the real toggle API."""
    _channel_toggle(api_url, "wechat", enabled)


def _feishu_toggle(api_url: str, enabled: bool) -> None:
    """Enable/disable the primary Feishu channel via the real toggle API."""
    _channel_toggle(api_url, "feishu", enabled)


def _channel_toggle(api_url: str, channel_type: str, enabled: bool) -> None:
    """Enable/disable a primary channel via the generic toggle API."""
    http_json(
        "PATCH",
        f"{api_url}/api/v1/channels/manage/{channel_type}/toggle",
        {"enabled": enabled},
    )


def _ensure_channel_enabled(api_url: str, channel_type: str) -> bool:
    """Toggle a primary channel on so its config card renders.

    Robustness guard: when the channel is persisted as disabled its whole
    configuration panel (delete button included) is hidden by design.
    Returns True when the channel had to be enabled (caller should restore).
    """
    statuses = http_json("GET", f"{api_url}/api/v1/channels/manage/status")
    entry = next(
        (s for s in statuses if isinstance(s, dict) and s.get("name") == channel_type),
        None,
    )
    if entry and entry.get("status") != "disabled":
        return False
    _channel_toggle(api_url, channel_type, True)
    return True


def _ensure_wechat_enabled(api_url: str) -> bool:
    """Toggle the primary WeChat channel on so its config card renders.

    Robustness guard: when the channel is persisted as disabled its whole
    configuration panel (delete button included) is hidden by design.
    Returns True when the channel had to be enabled (caller should restore).
    """
    return _ensure_channel_enabled(api_url, "wechat")


def _seed_wechat_instance(api_url: str) -> dict[str, str]:
    """Create a WeChat extra instance through the real instances API."""
    return _seed_instance(api_url, "wechat")


def _seed_instance(api_url: str, channel_type: str) -> dict[str, str]:
    """Create an extra instance of any channel type through the real instances API."""
    created = http_json(
        "POST",
        f"{api_url}{_INSTANCES_ENDPOINT}",
        {"channelType": channel_type, "displayName": "E2E Instance"},
    )
    assert isinstance(created, dict), created
    instance_id = str(created.get("instanceId") or "")
    assert instance_id, created
    return {"instanceId": instance_id, "channelName": str(created.get("channelName") or "")}


def _delete_instance_via_api(api_url: str, instance_id: str) -> None:
    """Best-effort cleanup through the real instances API."""
    http_json(
        "DELETE",
        f"{api_url}{_INSTANCES_ENDPOINT}/{instance_id}",
        expected_statuses=frozenset({200, 204, 404}),
    )


def _wechat_instances(api_url: str) -> list[dict[str, object]]:
    """Return the current WeChat instances from the real backend."""
    return _channel_instances(api_url, "wechat")


def _feishu_instances(api_url: str) -> list[dict[str, object]]:
    """Return the current Feishu instances from the real backend."""
    return _channel_instances(api_url, "feishu")


def _channel_instances(api_url: str, channel_type: str) -> list[dict[str, object]]:
    """Return the current instances of a channel type from the real backend."""
    listed = http_json("GET", f"{api_url}{_INSTANCES_ENDPOINT}?channel_type={channel_type}")
    assert isinstance(listed, list), listed
    return [i for i in listed if isinstance(i, dict)]


def _instances_fetch_probe_js(channel_type: str = "wechat") -> str:
    """Fetch the real instances API from the page context (same auth as the app).

    Uses the E2E runtime apiBase when present (PRIVATE mode), matching exactly
    what ``apiRequest`` resolves, so the response is what the frontend state is
    seeded from.
    """
    return f"""(() => {{
  const token = localStorage.getItem('auth_token') || '';
  const runtimeBase = ((window.__MYRM_E2E_RUNTIME__?.apiBase ?? window.__MYRM_E2E_API_BASE__) || '').replace(/\\/+$/, '');
  const url = runtimeBase
    ? `${{runtimeBase}}/api/v1/channels/manage/instances?channel_type={channel_type}`
    : '/api/v1/channels/manage/instances?channel_type={channel_type}';
  const xhr = new XMLHttpRequest();
  try {{
    xhr.open('GET', url, false);
    if (token) {{
      xhr.setRequestHeader('Authorization', `Bearer ${{token}}`);
    }}
    xhr.send();
    return {{
      runtimeBase,
      status: xhr.status,
      bodyLen: (xhr.responseText || '').length,
      body: (xhr.responseText || '').slice(0, 2500),
    }};
  }} catch (err) {{
    return {{ runtimeBase, err: String(err) }};
  }}
}})()"""


def _instance_ui_probe_js(instance_id: str, channel_type: str = "wechat") -> str:
    """Probe the extra-instance card: is its delete button / dialog still present?

    Also attributes each delete button to its container so we can tell whether a
    stale card lives in the responsive in-list detail (``lg:hidden``) or in the
    right-hand settings panel (``hidden lg:block``) — both mount a full
    config card on desktop.
    """
    return f"""(() => {{
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  const cancel = document.querySelector('[data-testid="confirm-dialog-cancel"]');
  const cards = Array.from(document.querySelectorAll('[aria-label^="delete-{channel_type}_"]')).map((b) => b.getAttribute('aria-label'));
  const delBtns = Array.from(document.querySelectorAll('[aria-label="delete-{channel_type}_{instance_id}"]'));
  const btnContexts = delBtns.map((b) => {{
    let el = b;
    let inListDetail = false;
    let inSidePanel = false;
    while (el && el !== document.body) {{
      const cls = el.className && typeof el.className === 'string' ? el.className : '';
      if (cls.includes('lg:hidden')) inListDetail = true;
      if (cls.includes('hidden lg:block')) inSidePanel = true;
      el = el.parentElement;
    }}
    return {{ inListDetail, inSidePanel }};
  }});
  const primaryBtn = document.querySelector('[aria-label="delete-{channel_type}"]');
  const noChannel = document.body.innerText || '';
  return {{
    hasDeleteBtn: delBtns.length > 0,
    deleteBtnCount: delBtns.length,
    btnContexts,
    dialogOpen: !!confirm && !!cancel,
    deleteBtns: cards,
    hasPrimaryBtn: !!primaryBtn,
    showsNoChannel: noChannel.includes('{channel_type}NoChannel') || noChannel.includes('not configured') || noChannel.includes('未配置'),
    bodyLen: (document.body?.innerText || '').length,
    viewportWidth: window.innerWidth,
    navType: performance.getEntriesByType('navigation')[0]?.type || 'navigate',
    href: location.href,
    bodyFull: (document.body.innerText || '').slice(0, 2000),
  }};
}})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wechat_delete_confirmation_flows() -> None:
    """Primary logout + extra-instance delete through the real confirmation dialog."""
    api_url = get_e2e_api_url()
    channels_url = f"{get_e2e_ui_url().rstrip('/')}{_CHANNELS_PATH}"
    prepare_e2e_ui_session(api_url)
    diag = _status_diagnostics(api_url)
    print(f"\n[channel-e2e] backend status diagnostics: {diag}")
    toggled = _ensure_wechat_enabled(api_url)

    seeded: dict[str, str] | None = None
    try:
        # ── Flow 1: primary WeChat card delete confirmation (logout) ──
        with open_settings_subroute(_CHANNELS_PATH, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page, recover_url=channels_url)
            nav = wait_for_state(client, page, _NAV_TO_WECHAT_JS, timeout_sec=120.0, page_url=channels_url)
            if nav.get("ready") is not True:
                nav["backendDiag"] = diag
            assert nav.get("ready") is True, nav

            # Cancel keeps the account.
            opened = client.evaluate(page, _OPEN_DELETE_DIALOG_JS, timeout_sec=30.0)
            assert isinstance(opened, dict) and opened.get("ok") is True, opened
            dlg = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
            assert dlg.get("ready") is True, dlg

            canceled = client.evaluate(page, _CANCEL_DIALOG_JS, timeout_sec=30.0)
            assert isinstance(canceled, dict) and canceled.get("ok") is True, canceled
            kept = wait_for_state(client, page, _DIALOG_CLOSED_KEEPING_JS, timeout_sec=30.0, page_url=channels_url)
            assert kept.get("ready") is True, kept

            # Re-open and confirm: dialog closes after the real logout API call.
            reopened = client.evaluate(page, _OPEN_DELETE_DIALOG_JS, timeout_sec=30.0)
            assert isinstance(reopened, dict) and reopened.get("ok") is True, reopened
            dlg2 = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
            assert dlg2.get("ready") is True, dlg2

            confirmed = client.evaluate(page, _CONFIRM_DIALOG_JS, timeout_sec=30.0)
            assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed
            closed = wait_for_state(
                client,
                page,
                _DIALOG_CLOSED_AFTER_CONFIRM_JS,
                timeout_sec=60.0,
                page_url=channels_url,
            )
            assert closed.get("ready") is True, closed

        # ── Flow 2: extra WeChat instance delete confirmation ──
        seeded = _seed_wechat_instance(api_url)
        instance_id = seeded["instanceId"]
        with open_settings_subroute(_CHANNELS_PATH, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page, recover_url=channels_url)
            nav2 = wait_for_state(client, page, _NAV_TO_WECHAT_JS, timeout_sec=120.0, page_url=channels_url)
            if nav2.get("ready") is not True:
                nav2["backendDiag"] = diag
            assert nav2.get("ready") is True, nav2

            extra = wait_for_state(
                client,
                page,
                _extra_instance_probe_js(instance_id),
                timeout_sec=60.0,
                page_url=channels_url,
            )
            if extra.get("ready") is not True:
                extra["backendInstancesBefore"] = _wechat_instances(api_url)
            assert extra.get("ready") is True, extra

            # Decisive evidence: what does the frontend's own fetch of
            # /instances return? The React state is seeded from this response,
            # so a mismatch here explains why the setInstances filter misses.
            try:
                fetch_probe = client.evaluate(page, _instances_fetch_probe_js(), timeout_sec=30.0)
                print(
                    f"[channel-e2e] Flow2 page-context instances fetch: "
                    f"{json.dumps(fetch_probe, ensure_ascii=False)}"
                )
                sys.stdout.flush()
            except (RuntimeError, TimeoutError, OSError) as exc:
                print(f"[channel-e2e] Flow2 page-context fetch failed: {str(exc)[:300]}")
                sys.stdout.flush()

            # Cancel keeps the instance.
            opened = client.evaluate(page, _extra_instance_open_js(instance_id), timeout_sec=30.0)
            assert isinstance(opened, dict) and opened.get("ok") is True, opened
            dlg = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
            assert dlg.get("ready") is True, dlg

            canceled = client.evaluate(page, _CANCEL_DIALOG_JS, timeout_sec=30.0)
            assert isinstance(canceled, dict) and canceled.get("ok") is True, canceled
            kept = wait_for_state(
                client,
                page,
                _extra_instance_probe_js(instance_id),
                timeout_sec=30.0,
                page_url=channels_url,
            )
            assert kept.get("ready") is True, kept

            # Re-open and confirm: card disappears after the real DELETE API call.
            reopened = client.evaluate(page, _extra_instance_open_js(instance_id), timeout_sec=30.0)
            assert isinstance(reopened, dict) and reopened.get("ok") is True, reopened
            dlg2 = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
            assert dlg2.get("ready") is True, dlg2

            confirmed = client.evaluate(page, _CONFIRM_DIALOG_JS, timeout_sec=30.0)
            assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed
            gone: dict[str, object]
            try:
                gone = wait_for_state(
                    client,
                    page,
                    _extra_instance_gone_js(instance_id),
                    timeout_sec=60.0,
                    page_url=channels_url,
                )
            except AssertionError:
                gone = {"ready": False}
            if gone.get("ready") is not True:
                gone["backendInstancesAfter"] = _wechat_instances(api_url)
                for probe_name, probe_js in (
                    ("goneProbe", _extra_instance_gone_js(instance_id)),
                    ("uiProbe", _instance_ui_probe_js(instance_id)),
                    ("fetchProbe", _instances_fetch_probe_js()),
                ):
                    try:
                        gone[probe_name] = client.evaluate(page, probe_js, timeout_sec=30.0)
                    except (RuntimeError, TimeoutError, OSError, AssertionError) as exc:
                        gone[probe_name] = {"evaluateErr": str(exc)[:300]}
                print(f"[channel-e2e] Flow2 gone diagnostics: {json.dumps(gone, ensure_ascii=False)}")
                sys.stdout.flush()
            assert gone.get("ready") is True, gone

            # The instance is really gone from the backend too.
            assert all(
                i.get("instanceId") != instance_id for i in _wechat_instances(api_url)
            )

        # ── Flow 3: delete failure keeps the confirm dialog open ──
        # A concurrent removal (out-of-band API delete) makes the UI confirm hit
        # a backend 404. ConfirmDialog must NOT close: the user sees the error
        # toast and can retry or cancel.
        seeded = _seed_wechat_instance(api_url)
        instance3 = seeded["instanceId"]
        with open_settings_subroute(_CHANNELS_PATH, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page, recover_url=channels_url)
            nav3 = wait_for_state(client, page, _NAV_TO_WECHAT_JS, timeout_sec=120.0, page_url=channels_url)
            assert nav3.get("ready") is True, nav3

            extra3 = wait_for_state(
                client,
                page,
                _extra_instance_probe_js(instance3),
                timeout_sec=60.0,
                page_url=channels_url,
            )
            assert extra3.get("ready") is True, extra3

            # Open the dialog, then remove the instance out-of-band so the
            # confirm action hits a 404.
            opened = client.evaluate(page, _extra_instance_open_js(instance3), timeout_sec=30.0)
            assert isinstance(opened, dict) and opened.get("ok") is True, opened
            dlg = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
            assert dlg.get("ready") is True, dlg

            _delete_instance_via_api(api_url, instance3)

            confirmed = client.evaluate(page, _CONFIRM_DIALOG_JS, timeout_sec=30.0)
            assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed
            # On failure the dialog must stay open (ConfirmDialog catches and
            # keeps it) and the confirm request must settle (buttons re-enabled),
            # so the user can retry or cancel.
            still_open = wait_for_state(
                client,
                page,
                _DIALOG_STAYS_OPEN_JS,
                timeout_sec=45.0,
                page_url=channels_url,
            )
            assert still_open.get("ready") is True, still_open

            # Cancel then closes the dialog; the stale card remains in the UI
            # (the frontend list is not auto-refreshed after a failed delete).
            canceled = client.evaluate(page, _CANCEL_DIALOG_JS, timeout_sec=30.0)
            assert isinstance(canceled, dict) and canceled.get("ok") is True, canceled
            closed: dict[str, object]
            try:
                closed = wait_for_state(
                    client,
                    page,
                    _extra_instance_dialog_closed_js(instance3),
                    timeout_sec=30.0,
                    page_url=channels_url,
                )
            except AssertionError:
                closed = {"ready": False}
            if closed.get("ready") is not True:
                closed["backendInstancesAfter"] = _wechat_instances(api_url)
                for probe_name, probe_js in (
                    ("closedProbe", _extra_instance_dialog_closed_js(instance3)),
                    ("uiProbe", _instance_ui_probe_js(instance3)),
                ):
                    try:
                        closed[probe_name] = client.evaluate(page, probe_js, timeout_sec=30.0)
                    except (RuntimeError, TimeoutError, OSError, AssertionError) as exc:
                        closed[probe_name] = {"evaluateErr": str(exc)[:300]}
                print(f"[channel-e2e] Flow3 closed diagnostics: {json.dumps(closed, ensure_ascii=False)}")
                sys.stdout.flush()
            assert closed.get("ready") is True, closed
    finally:
        if seeded:
            _delete_instance_via_api(api_url, seeded["instanceId"])
        if toggled:
            try:
                _wechat_toggle(api_url, False)
            except RuntimeError:
                pass
