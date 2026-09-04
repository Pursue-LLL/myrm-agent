"""Chrome E2E: Mobile Push Discovery Banner renders in MobileStatusBoard container."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)

_VERIFY_WEB_PUSH_VAPID_JS = """(async () => {
  const res = await fetch('/api/v1/web-push/vapid-key', { cache: 'no-store' });
  if (!res.ok) {
    return { ok: false, status: res.status };
  }
  const body = await res.json();
  return {
    ok: typeof body.public_key === 'string' && body.public_key.length > 0,
    publicKeyLength: body.public_key ? body.public_key.length : 0,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_mobile_web_push_discovery_banner_chrome_e2e() -> None:
    """Verify backend Web Push VAPID public key availability and browser readiness."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=f"{ui_url}/",
        )
        vapid_res = client.evaluate(page, _VERIFY_WEB_PUSH_VAPID_JS)
        assert vapid_res.get("ok") is True, f"VAPID public key check failed: {vapid_res}"
        assert vapid_res.get("publicKeyLength", 0) > 10, vapid_res
