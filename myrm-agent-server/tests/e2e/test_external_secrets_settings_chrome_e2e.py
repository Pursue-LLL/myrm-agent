"""Chrome E2E: External secrets vault validation endpoint and Settings models route contract."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)

_SETTINGS_MODELS_SHELL_STATE = """(() => {
  try {
    const bodyText = document.body?.innerText || '';
    return {
      ready:
        location.pathname.includes('/settings') &&
        bodyText.length > 20 &&
        !!document.querySelector('[data-testid="settings-layout"]'),
      pathname: location.pathname,
      bodyLength: bodyText.length,
    };
  } catch (err) {
    return { ready: false, err: String(err) };
  }
})()"""

_VALIDATE_SECRET_IN_BROWSER_JS = """(() => {
  return new Promise((resolve) => {
    fetch('/api/v1/integrations/llm/credential-pool/validate-secret-reference', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reference: 'op://Enterprise/OpenAI/api_key' })
    })
    .then(r => r.json())
    .then(data => resolve({ ok: true, data }))
    .catch(err => resolve({ ok: false, err: String(err) }));
  });
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_external_secrets_settings_route_and_api_contract() -> None:
    """Verify Settings route opens in Chrome and external secret validator API responds gracefully."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    with open_settings_subroute("/settings/models") as (client, page):
        state = wait_for_state(
            client,
            page,
            _SETTINGS_MODELS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )
        assert state.get("ready") is True, f"Settings models shell not ready: {state}"

        # Evaluate the live in-browser fetch towards the new external secret validation endpoint
        result = client.evaluate(page, _VALIDATE_SECRET_IN_BROWSER_JS)
        assert result.get("ok") is True, f"In-page fetch failed: {result}"
        payload = result.get("data", {})
        assert payload.get("success") is True, f"API returned non-success: {payload}"
        data = payload.get("data", {})
        # Should gracefully detect missing CLI or unauthenticated CLI without crashing
        assert "valid" in data, f"Missing 'valid' field in payload: {data}"
        assert data.get("valid") is False
        assert "op" in data.get("error", "") or "not found" in data.get("error", "")
