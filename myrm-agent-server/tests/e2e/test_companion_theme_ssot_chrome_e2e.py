"""Chrome MCP smoke: Appearance preset switch updates workspace CSS tokens (companion SSOT chain)."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_READ_THEME_TOKENS = """(() => {
  const root = document.documentElement;
  const styles = getComputedStyle(root);
  return {
    profileId: root.getAttribute('data-myrm-theme-profile'),
    primary: styles.getPropertyValue('--primary').trim(),
    accentWarm: styles.getPropertyValue('--accent-warm').trim(),
  };
})()"""

_CLICK_ROSE_PRESET = """(() => {
  const labels = ['Rose', '玫瑰', 'ローズ'];
  const button = Array.from(document.querySelectorAll('button')).find((node) => {
    const text = (node.textContent || '').trim();
    return labels.some((label) => text.includes(label));
  });
  if (!button) {
    return { ok: false, err: 'rose_preset_missing' };
  }
  button.click();
  return { ok: true };
})()"""

_WAIT_ROSE_PROFILE = """(() => {
  const root = document.documentElement;
  const profileId = root.getAttribute('data-myrm-theme-profile');
  const primary = getComputedStyle(root).getPropertyValue('--primary').trim().toLowerCase();
  const rosePrimary = primary === '#c4567a' || primary === '#f472b6';
  return {
    ready: profileId === 'preset-rose' && rosePrimary,
    profileId,
    primary,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode='SHARED', access_scope='READ', workload='STANDARD'
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_appearance_preset_updates_workspace_primary_token() -> None:
    """Switching Appearance preset must recompile --primary on documentElement."""
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route('/settings/preferences')
    with open_mcp_page(
        f'{get_e2e_ui_url()}/settings/preferences',
        timeout_ms=90_000,
    ) as (client, page):
        dismiss_blocking_modals(client, page)

        before = client.evaluate(page, _READ_THEME_TOKENS, timeout_sec=30.0)
        assert isinstance(before, dict), before
        before_primary = str(before.get('primary') or '').lower()

        click_state = client.evaluate(page, _CLICK_ROSE_PRESET, timeout_sec=30.0)
        assert isinstance(click_state, dict), click_state
        assert click_state.get('ok') is True, click_state

        after = wait_for_state(
            client,
            page,
            _WAIT_ROSE_PROFILE,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert after.get('ready') is True, after
        after_primary = str(after.get('primary') or '').lower()
        assert after_primary != before_primary, {'before': before, 'after': after}
