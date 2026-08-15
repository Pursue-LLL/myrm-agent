"""Chrome MCP E2E: channel instance delete confirmation flows.

Covers the real-browser wiring behind the settings "delete instance" confirmation
dialog (``ConfirmDialog``) for WeChat multi-account:

- Primary account logout confirmation: open the delete dialog on the primary
  WeChat card, cancel keeps the account, confirm triggers the real
  ``POST /wechat-logout`` and closes the dialog.
- Extra instance delete confirmation: seed a WeChat extra instance through the
  real ``POST /instances`` API, delete it through the UI confirmation dialog,
  and verify the card disappears from the settings page.

Both flows drive the real WebUI (settings → channels → WeChat) via Chrome MCP
and assert on real API effects (logout / instance removal) where applicable.

Execution mode: SHARED + NAMESPACE_WRITE (instance list writes are namespace
scoped; no global config mutation).
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
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
  };
})()"""

# Confirm triggers logout and the dialog closes after the API round-trip.
_DIALOG_CLOSED_AFTER_CONFIRM_JS = """(() => {
  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  return {
    ready: !confirm,
    dialogClosed: !confirm,
    bodySnippet: (document.body.innerText || '').slice(0, 300),
  };
})()"""


def _extra_instance_probe_js(instance_id: str) -> str:
    """Return a probe that detects the extra-instance card delete button."""
    return f"""(() => {{
  const delBtn = document.querySelector('[aria-label="delete-wechat_{instance_id}"]');
  return {{
    ready: !!delBtn,
    hasDeleteBtn: !!delBtn,
    bodySnippet: (document.body.innerText || '').slice(0, 300),
  }};
}})()"""


def _extra_instance_gone_js(instance_id: str) -> str:
    """Return a probe that confirms the extra-instance card is gone."""
    return f"""(() => {{
  const delBtn = document.querySelector('[aria-label="delete-wechat_{instance_id}"]');
  return {{
    ready: !delBtn,
    instanceGone: !delBtn,
  }};
}})()"""


def _seed_wechat_instance(api_url: str) -> dict[str, str]:
    """Create a WeChat extra instance through the real instances API."""
    created = http_json(
        "POST",
        f"{api_url}{_INSTANCES_ENDPOINT}",
        {"channelType": "wechat", "displayName": "E2E Instance"},
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


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_wechat_primary_logout_confirmation() -> None:
    """Primary WeChat card: cancel keeps the account; confirm logs out via real API."""
    api_url = get_e2e_api_url()
    channels_url = f"{get_e2e_ui_url().rstrip('/')}{_CHANNELS_PATH}"
    prepare_e2e_ui_session(api_url)

    with open_settings_subroute(_CHANNELS_PATH, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=channels_url)
        nav = wait_for_state(client, page, _NAV_TO_WECHAT_JS, timeout_sec=120.0, page_url=channels_url)
        assert nav.get("ready") is True, nav

        # Cancel keeps the account.
        opened = client.evaluate(page, _OPEN_DELETE_DIALOG_JS, timeout_sec=30.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened
        dlg = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
        assert dlg.get("ready") is True, dlg

        canceled = client.evaluate(
            page,
            """(() => {
              const cancel = document.querySelector('[data-testid="confirm-dialog-cancel"]');
              if (!cancel) return { ok: false, err: 'cancel-not-found' };
              cancel.click();
              return { ok: true };
            })()""",
            timeout_sec=30.0,
        )
        assert isinstance(canceled, dict) and canceled.get("ok") is True, canceled
        kept = wait_for_state(client, page, _DIALOG_CLOSED_KEEPING_JS, timeout_sec=30.0, page_url=channels_url)
        assert kept.get("ready") is True, kept

        # Re-open and confirm: dialog closes after the real logout API call.
        reopened = client.evaluate(page, _OPEN_DELETE_DIALOG_JS, timeout_sec=30.0)
        assert isinstance(reopened, dict) and reopened.get("ok") is True, reopened
        dlg2 = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
        assert dlg2.get("ready") is True, dlg2

        confirmed = client.evaluate(
            page,
            """(() => {
              const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
              if (!confirm) return { ok: false, err: 'confirm-not-found' };
              confirm.click();
              return { ok: true };
            })()""",
            timeout_sec=30.0,
        )
        assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed
        closed = wait_for_state(
            client,
            page,
            _DIALOG_CLOSED_AFTER_CONFIRM_JS,
            timeout_sec=60.0,
            page_url=channels_url,
        )
        assert closed.get("ready") is True, closed


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_wechat_extra_instance_delete_confirmation() -> None:
    """Extra WeChat instance: seeded via real API, deleted through the UI dialog."""
    api_url = get_e2e_api_url()
    channels_url = f"{get_e2e_ui_url().rstrip('/')}{_CHANNELS_PATH}"
    prepare_e2e_ui_session(api_url)

    seeded = _seed_wechat_instance(api_url)
    instance_id = seeded["instanceId"]
    try:
        with open_settings_subroute(_CHANNELS_PATH, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page, recover_url=channels_url)
            nav = wait_for_state(client, page, _NAV_TO_WECHAT_JS, timeout_sec=120.0, page_url=channels_url)
            assert nav.get("ready") is True, nav

            extra = wait_for_state(
                client,
                page,
                _extra_instance_probe_js(instance_id),
                timeout_sec=60.0,
                page_url=channels_url,
            )
            assert extra.get("ready") is True, extra

            # Cancel keeps the instance.
            opened = client.evaluate(
                page,
                f"""(() => {{
                  const delBtn = document.querySelector('[aria-label="delete-wechat_{instance_id}"]');
                  if (!delBtn) return {{ ok: false, err: 'delete-btn-not-found' }};
                  delBtn.click();
                  return {{ ok: true }};
                }})()""",
                timeout_sec=30.0,
            )
            assert isinstance(opened, dict) and opened.get("ok") is True, opened
            dlg = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
            assert dlg.get("ready") is True, dlg

            canceled = client.evaluate(
                page,
                """(() => {
                  const cancel = document.querySelector('[data-testid="confirm-dialog-cancel"]');
                  if (!cancel) return { ok: false, err: 'cancel-not-found' };
                  cancel.click();
                  return { ok: true };
                })()""",
                timeout_sec=30.0,
            )
            assert isinstance(canceled, dict) and canceled.get("ok") is True, canceled
            kept = wait_for_state(client, page, _extra_instance_probe_js(instance_id), timeout_sec=30.0, page_url=channels_url)
            assert kept.get("ready") is True, kept

            # Re-open and confirm: card disappears after the real DELETE API call.
            reopened = client.evaluate(
                page,
                f"""(() => {{
                  const delBtn = document.querySelector('[aria-label="delete-wechat_{instance_id}"]');
                  if (!delBtn) return {{ ok: false, err: 'delete-btn-not-found' }};
                  delBtn.click();
                  return {{ ok: true }};
                }})()""",
                timeout_sec=30.0,
            )
            assert isinstance(reopened, dict) and reopened.get("ok") is True, reopened
            dlg2 = wait_for_state(client, page, _DIALOG_OPEN_STATE_JS, timeout_sec=30.0)
            assert dlg2.get("ready") is True, dlg2

            confirmed = client.evaluate(
                page,
                """(() => {
                  const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]');
                  if (!confirm) return { ok: false, err: 'confirm-not-found' };
                  confirm.click();
                  return { ok: true };
                })()""",
                timeout_sec=30.0,
            )
            assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed
            gone = wait_for_state(
                client,
                page,
                _extra_instance_gone_js(instance_id),
                timeout_sec=60.0,
                page_url=channels_url,
            )
            assert gone.get("ready") is True, gone

            # The instance is really gone from the backend too.
            listed = http_json(
                "GET",
                f"{api_url}{_INSTANCES_ENDPOINT}?channel_type=wechat",
            )
            assert isinstance(listed, list), listed
            assert all(i.get("instanceId") != instance_id for i in listed if isinstance(i, dict))
    finally:
        _delete_instance_via_api(api_url, instance_id)
