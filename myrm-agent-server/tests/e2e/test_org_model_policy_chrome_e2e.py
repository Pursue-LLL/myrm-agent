"""Chrome MCP E2E: Org model policy UI enforcement in model picker.

Verifies that when an org model policy is active, restricted models
appear as disabled/grayed-out in the model picker popover.

Uses PRIVATE execution + NAMESPACE_WRITE to seed policy via API then
inspect the model picker UI state.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

# Chrome E2E seed (.env.test) typically exposes minimax/* + openai-like/* providers.
_POLICY_SEED_PATTERNS = ["minimax/*"]


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
    """With org model policy active, non-matching models appear disabled."""
    ui_base = get_e2e_ui_url()
    warm_ui_route("/")
    api_base = get_e2e_api_url()
    _sync_org_model_policy(api_base, patterns=_POLICY_SEED_PATTERNS)
    try:
        with open_mcp_page(f"{ui_base}/", timeout_ms=90_000) as (client, page):
            state = wait_for_state(
                client, page, _MODEL_PICKER_POLICY_STATE_JS, timeout_sec=120.0
            )
            assert state.get("ready") is True, f"Model picker not ready: {state}"
            assert state.get("totalModels", 0) > 0, "No models found in picker"

            disabled = state.get("disabledModels", [])
            enabled = state.get("enabledModels", [])

            assert len(enabled) > 0, "Expected minimax/* models to remain selectable"
            assert len(disabled) > 0, "Expected non-minimax models to be greyed out"
            for model_name in enabled:
                model_lower = (model_name or "").lower()
                assert "minimax" in model_lower, (
                    f"Enabled model '{model_name}' should match minimax/*"
                )
            for model_name in disabled:
                model_lower = (model_name or "").lower()
                assert "minimax" not in model_lower, (
                    f"Disabled model '{model_name}' should not match minimax/*"
                )
    finally:
        _sync_org_model_policy(api_base, patterns=[])
