"""Chrome MCP E2E: Org model policy UI enforcement in model picker.

Verifies the model picker reflects the org model policy: with an unrestricted
policy every model stays selectable, and with a whitelist pattern that matches
nothing every model is greyed out. Two phases keep the assertions meaningful
under the current single-provider ``.env.test`` (BASIC_MODEL/LITE_MODEL share
the same openai-like provider) without assuming a minimax provider exists.

Uses PRIVATE execution + NAMESPACE_WRITE to seed policy via API then
inspect the model picker UI state.
"""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

# Matches no provider/model; every seeded model must be greyed out.
_NON_MATCHING_PATTERN = "__e2e_nonexistent__/*"


def _sync_org_model_policy(api_base: str, *, patterns: list[str]) -> None:
    resp = http_json(
        "POST",
        f"{api_base}/api/admin/org-model-policy-sync",
        body={"allowed_patterns": patterns},
    )
    assert isinstance(resp, dict) and resp.get("status") == "synced", resp


_MODEL_PICKER_POLICY_STATE_JS = """(() => {
  const trigger = document.querySelector('[data-testid="model-picker-trigger"]');
  if (trigger) {
    const popover = document.querySelector('[data-testid="model-picker-popover"]');
    if (!popover) {
      trigger.click();
      return { ready: false, reason: 'opening_picker' };
    }
  }

  const picker = document.querySelector('[data-testid="model-picker-popover"]')
    || document.querySelector('[data-testid="model-selector"]');
  if (!picker) return { ready: false, reason: 'picker_not_found' };

  const items = picker.querySelectorAll('[data-testid*="model-item"]');
  if (items.length === 0) return { ready: false, reason: 'no_items' };

  const results = [];
  items.forEach(item => {
    const name = item.getAttribute('data-model-name') || item.textContent?.trim();
    const disabled = item.hasAttribute('disabled')
      || item.getAttribute('aria-disabled') === 'true'
      || item.classList.contains('opacity-40')
      || item.classList.contains('opacity-50')
      || item.classList.contains('pointer-events-none')
      || item.classList.contains('cursor-not-allowed');
    results.push({ name, disabled });
  });

  return {
    ready: true,
    totalModels: results.length,
    disabledModels: results.filter(r => r.disabled).map(r => r.name),
    enabledModels: results.filter(r => !r.disabled).map(r => r.name),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.timeout(300)
def test_model_picker_shows_policy_restricted_models_as_disabled() -> None:
    """Policy whitelist greys out non-matching models in the picker."""
    ui_base = get_e2e_ui_url()
    warm_ui_route("/")
    api_base = get_e2e_api_url()

    try:
        # Phase 1: unrestricted baseline — every model stays selectable.
        _sync_org_model_policy(api_base, patterns=[])
        with open_mcp_page(f"{ui_base}/", timeout_ms=90_000) as (client, page):
            state = wait_for_state(client, page, _MODEL_PICKER_POLICY_STATE_JS, timeout_sec=120.0)
            assert state.get("ready") is True, f"Model picker not ready: {state}"
            assert state.get("totalModels", 0) > 0, "No models found in picker"
            assert len(state.get("enabledModels", [])) > 0, "Unrestricted policy must keep models selectable"
            assert len(state.get("disabledModels", [])) == 0, "Unrestricted baseline must not grey out any model"

            # Phase 2: a non-matching whitelist greys out every model. Reload the
            # page so the picker reopens and refetches the updated policy, then
            # give the async policy fetch a moment to land before asserting.
            _sync_org_model_policy(api_base, patterns=[_NON_MATCHING_PATTERN])
            reload_mcp_page(client, page, target_url=f"{ui_base}/", timeout_ms=60_000)
            time.sleep(2)
            state = wait_for_state(client, page, _MODEL_PICKER_POLICY_STATE_JS, timeout_sec=120.0)
            assert state.get("ready") is True, f"Model picker not ready: {state}"
            assert len(state.get("disabledModels", [])) > 0, "Restricted policy must grey out non-matching models"
            assert len(state.get("enabledModels", [])) == 0, "Non-matching policy must block every model"
    finally:
        # Leave the shared stack unrestricted.
        _sync_org_model_policy(api_base, patterns=[])
