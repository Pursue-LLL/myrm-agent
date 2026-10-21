"""Chrome E2E: Codex migration wiki completion lane handoff UI."""

from __future__ import annotations

import os
import sys

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
)

_WAIT_AND_RENDER_LANE_JS = """(async () => {
  for (let attempt = 0; attempt < 160; attempt += 1) {
    const bridge = window.__MYRM_E2E_MIGRATION__;
    if (bridge) {
      bridge.showCodexCompletionLane({
        targetAgentId: 'agent-e2e-codex',
        vaultCandidate: {
          path: '/tmp/e2e-obsidian-vault',
          label: 'Codex Obsidian vault',
          has_obsidian_config: true,
          markdown_file_count: 4,
        },
      });
      for (let renderAttempt = 0; renderAttempt < 80; renderAttempt += 1) {
        const lane = document.querySelector('[data-testid="codex-wiki-completion-lane"]');
        if (lane) {
          return {
            ready: true,
            hasVaultHint: !!document.querySelector('[data-testid="codex-completion-vault-hint"]'),
            hasImportBtn: !!document.querySelector('[data-testid="codex-completion-import-wiki"]'),
            hasWikiBridge: typeof window.__MYRM_E2E_WIKI__ !== 'undefined',
          };
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      return { ready: false, err: 'lane-timeout', hasWikiBridge: typeof window.__MYRM_E2E_WIKI__ !== 'undefined' };
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return {
    ready: false,
    err: 'no-bridge',
    hasWikiBridge: typeof window.__MYRM_E2E_WIKI__ !== 'undefined',
    hasChatBridge: typeof window.__MYRM_E2E_CHAT__ !== 'undefined',
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_codex_wiki_completion_lane_handoff() -> None:
    """Migration bridge renders Codex completion lane with vault hint + import CTA."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    wiki_url = f"{ui_url.rstrip('/')}/settings/wiki"
    with open_wiki_settings_mcp_page(
        wiki_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=wiki_url)
        state = client.evaluate(
            page,
            _WAIT_AND_RENDER_LANE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
            await_promise=True,
        )
        assert isinstance(state, dict), state
        assert state.get("ready") is True, state
        assert state.get("hasVaultHint") is True, state
        assert state.get("hasImportBtn") is True, state
