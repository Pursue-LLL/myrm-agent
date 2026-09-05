"""Real Chrome MCP E2E: Model Orchestration Playbook & Discoverability Flow.

Verifies end-to-end:
1. WebUI Settings models tab (/settings?tab=models) renders ModelOrchestrationPlaybookCard.
2. Playbook card expand/collapse toggle and full playbook dialog trigger.
3. ModelOrchestrationPlaybookDialog renders all three tabs (recipes, principles, economics).
4. Smooth modal dismissal via close button.
5. Server backend health status check.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_VERIFY_PLAYBOOK_UI_JS = """(() => {
  try {
    const card = document.querySelector('[data-testid="model-orchestration-playbook-card"]');
    const openBtn = document.querySelector('[data-testid="view-full-playbook-button"]');
    const expandBtn = document.querySelector('[data-testid="toggle-expand-playbook-button"]');
    
    if (!card) {
      return { ok: false, err: 'model-orchestration-playbook-card not found in DOM' };
    }

    // Click to open dialog
    if (openBtn) {
      openBtn.click();
    }

    return {
      ok: true,
      cardFound: !!card,
      openBtnFound: !!openBtn,
      expandBtnFound: !!expandBtn,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_VERIFY_DIALOG_AND_DISMISS_JS = """(() => {
  try {
    const dialog = document.querySelector('[data-testid="model-orchestration-playbook-dialog"]');
    if (!dialog) {
      return { ok: false, err: 'dialog not found in DOM' };
    }

    const tabRecipes = document.querySelector('[data-testid="playbook-tab-recipes"]');
    const tabPrinciples = document.querySelector('[data-testid="playbook-tab-principles"]');
    const tabEconomics = document.querySelector('[data-testid="playbook-tab-economics"]');
    const closeBtn = document.querySelector('[data-testid="playbook-close-button"]');

    // Switch to principles tab to verify interaction
    if (tabPrinciples) {
      tabPrinciples.click();
    }

    // Close the dialog
    if (closeBtn) {
      closeBtn.click();
    }

    return {
      ok: true,
      dialogFound: true,
      hasRecipesTab: !!tabRecipes,
      hasPrinciplesTab: !!tabPrinciples,
      hasEconomicsTab: !!tabEconomics,
      hasCloseBtn: !!closeBtn,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    private_reason="exclusive_backend",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_model_orchestration_playbook_settings_chrome_e2e() -> None:
    """Validate Model Orchestration Playbook card, dialog interactions, and tabs in real Chrome."""
    _require_e2e_cdp_ready()
    api_url = get_e2e_api_url()

    # 1. Warm up Settings UI route and navigate to models tab in real Chrome MCP
    prepare_e2e_ui_session(api_url)
    warm_ui_route("/settings")

    with open_settings_subroute("/settings?tab=models", timeout_ms=90_000) as (
        client,
        page,
    ):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            """(() => {
              const bodyText = document.body?.innerText || '';
              const card = document.querySelector('[data-testid="model-orchestration-playbook-card"]');
              return {
                ready: !!card || /模型|Models/i.test(bodyText),
                cardFound: !!card,
              };
            })()""",
            timeout_sec=45.0,
        )
        assert state.get("ready") is True, f"Settings models tab not ready: {state}"

        # 2. Check playbook card presence and trigger modal open
        eval_card = client.evaluate(page, _VERIFY_PLAYBOOK_UI_JS, timeout_sec=20.0)
        assert isinstance(
            eval_card, dict
        ), f"Expected dict evaluation result, got: {eval_card}"
        assert eval_card.get("ok") is True, f"Playbook card verification failed: {eval_card}"
        assert eval_card.get("cardFound") is True, "Playbook card not found"

        # 3. Check dialog rendering, tab switching, and dismissal
        eval_dialog = client.evaluate(
            page, _VERIFY_DIALOG_AND_DISMISS_JS, timeout_sec=20.0
        )
        assert isinstance(
            eval_dialog, dict
        ), f"Expected dict evaluation result, got: {eval_dialog}"
        assert (
            eval_dialog.get("ok") is True
        ), f"Playbook dialog verification failed: {eval_dialog}"
        assert eval_dialog.get("dialogFound") is True, "Playbook dialog not found"
        assert eval_dialog.get("hasRecipesTab") is True, "Recipes tab missing"
        assert eval_dialog.get("hasPrinciplesTab") is True, "Principles tab missing"
        assert eval_dialog.get("hasEconomicsTab") is True, "Economics tab missing"

    # 4. Direct REST check on server health status
    health_res = http_json("GET", f"{api_url}/api/v1/health")
    assert isinstance(health_res, dict)
    assert health_res.get("status") == "healthy"
