"""Chrome E2E: Lifecycle Outbound Webhook settings (READ + WRITE).

READ: same-origin list probe on Integration Catalog.
WRITE: full create → ping → update → clear_agent_scope → delete via browser fetch on settings page.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    warm_ui_route,
)

_WEBHOOK_SETTINGS_CHECK_JS = """(async () => {
  const res = await fetch('/api/v1/lifecycle-webhooks', { cache: 'no-store' });
  if (!res.ok) {
    return { ok: false, status: res.status };
  }
  const hooks = await res.json();
  return {
    ok: Array.isArray(hooks),
    count: hooks.length,
  };
})()"""

_WEBHOOK_CRUD_FLOW_JS = """(async () => {
  const suffix = Date.now().toString(36);
  const createRes = await fetch('/api/v1/lifecycle-webhooks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: `E2E Hook ${suffix}`,
      url: 'https://example.com/api/webhook',
      events: ['session_completed', 'session_failed'],
      is_active: true,
    }),
  });
  if (!createRes.ok) {
    return { ok: false, step: 'create', status: createRes.status, body: await createRes.text() };
  }
  const created = await createRes.json();
  const id = created.id;
  if (!id) {
    return { ok: false, step: 'create', err: 'missing id' };
  }

  const pingRes = await fetch(`/api/v1/lifecycle-webhooks/${id}/ping`, { method: 'POST' });
  if (!pingRes.ok) {
    return { ok: false, step: 'ping', status: pingRes.status };
  }
  const pingBody = await pingRes.json();
  if (typeof pingBody.success !== 'boolean') {
    return { ok: false, step: 'ping', err: 'invalid ping body' };
  }

  const updateRes = await fetch(`/api/v1/lifecycle-webhooks/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: `E2E Hook Updated ${suffix}`, events: ['session_completed'] }),
  });
  if (!updateRes.ok) {
    return { ok: false, step: 'update', status: updateRes.status };
  }

  const emptyEventsRes = await fetch(`/api/v1/lifecycle-webhooks/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ events: [] }),
  });
  if (emptyEventsRes.status !== 422) {
    return { ok: false, step: 'reject_empty_events', status: emptyEventsRes.status };
  }

  const deleteRes = await fetch(`/api/v1/lifecycle-webhooks/${id}`, { method: 'DELETE' });
  if (deleteRes.status !== 204) {
    return { ok: false, step: 'delete', status: deleteRes.status };
  }

  return { ok: true, id, pingSuccess: pingBody.success };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_lifecycle_webhook_settings_chrome_e2e() -> None:
    """Browser same-origin fetch verifies lifecycle webhook settings endpoint accessibility in WebUI."""
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/integrationCatalog")
    with open_settings_subroute("/settings/integrationCatalog", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        browser_body = client.evaluate(page, _WEBHOOK_SETTINGS_CHECK_JS)
        assert browser_body.get("ok") is True, browser_body


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_lifecycle_webhook_settings_crud_flow_chrome_e2e() -> None:
    """Browser on Integration Catalog performs lifecycle webhook CRUD + saved ping + empty-events guard."""
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/integrationCatalog")
    with open_settings_subroute("/settings/integrationCatalog", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        browser_body = client.evaluate(page, _WEBHOOK_CRUD_FLOW_JS, timeout_sec=60.0)
        assert browser_body.get("ok") is True, browser_body
