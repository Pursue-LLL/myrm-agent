"""Chrome MCP smoke: Appearance preset switch updates workspace CSS tokens (companion SSOT chain)."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

# Visible preset labels across supported locales (en / zh / ja).
_OFFICIAL_DEFAULT_LABELS = ["Teal & Orange", "青橙", "ティール＆オレンジ"]
_ROSE_LABELS = ["Rose", "玫瑰", "ローズ"]

_OFFICIAL_DEFAULT_PROFILE_ID = "official-default"
_ROSE_PROFILE_ID = "preset-rose"
_ROSE_PRIMARY_LIGHT = "#f472b6"

_READ_THEME_TOKENS = """(() => {
  const root = document.documentElement;
  const styles = getComputedStyle(root);
  return {
    profileId: root.getAttribute('data-myrm-theme-profile'),
    primary: styles.getPropertyValue('--primary').trim(),
    accentWarm: styles.getPropertyValue('--accent-warm').trim(),
  };
})()"""


def _wait_preset_button_snippet(labels: list[str]) -> str:
    """Wait until a preset button whose visible text contains any label is present."""
    return f"""(() => {{
  const labels = {json.dumps(labels)};
  const button = Array.from(document.querySelectorAll('button')).find((node) => {{
    const text = (node.textContent || '').trim();
    return labels.some((label) => text.includes(label));
  }});
  return {{
    ready: !!button,
    bodyLen: document.body ? document.body.innerText.length : -1,
  }};
}})()"""


def _click_preset_snippet(labels: list[str]) -> str:
    """Click the first preset button whose visible text contains any label."""
    return f"""(() => {{
  const labels = {json.dumps(labels)};
  const button = Array.from(document.querySelectorAll('button')).find((node) => {{
    const text = (node.textContent || '').trim();
    return labels.some((label) => text.includes(label));
  }});
  if (!button) {{ return {{ ok: false, err: 'preset_button_missing' }}; }}
  button.click();
  return {{ ok: true }};
}})()"""


def _wait_profile_snippet(profile_id: str, *, primary: str | None = None) -> str:
    """Wait until data-myrm-theme-profile equals profile_id (optionally the --primary token)."""
    primary_clause = "true" if primary is None else f"primary === '{primary}'"
    return f"""(() => {{
  const root = document.documentElement;
  const profileId = root.getAttribute('data-myrm-theme-profile');
  const primary = getComputedStyle(root).getPropertyValue('--primary').trim().toLowerCase();
  return {{ ready: profileId === '{profile_id}' && {primary_clause}, profileId, primary }};
}})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_appearance_preset_updates_workspace_primary_token() -> None:
    """Switching Appearance preset must recompile --primary on documentElement.

    Writes the workspace `activeThemeProfileId` (NAMESPACE_WRITE). The profile
    persists across runs, so the test is idempotent: it resets to the official
    default baseline when the workspace is already on Rose, then switches to Rose
    and asserts the target state. The shared workspace is restored to the official
    default on exit so the theme does not leak to parallel sessions.
    """
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/preferences")
    with open_settings_subroute(
        "/settings/preferences",
        timeout_ms=90_000,
    ) as (client, page):
        dismiss_blocking_modals(client, page)

        # Preset buttons render only after client-side hydration (~6s after open).
        wait_for_state(
            client,
            page,
            _wait_preset_button_snippet(_ROSE_LABELS),
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )

        baseline = client.evaluate(page, _READ_THEME_TOKENS, timeout_sec=30.0)
        assert isinstance(baseline, dict), baseline

        try:
            # Re-runs may already be on Rose (the profile persists in the shared
            # workspace); reset to the official default so the switch below has an
            # observable effect instead of asserting a no-op.
            if baseline.get("profileId") == _ROSE_PROFILE_ID:
                click = client.evaluate(
                    page,
                    _click_preset_snippet(_OFFICIAL_DEFAULT_LABELS),
                    timeout_sec=30.0,
                )
                assert isinstance(click, dict) and click.get("ok") is True, click
                default_state = wait_for_state(
                    client,
                    page,
                    _wait_profile_snippet(_OFFICIAL_DEFAULT_PROFILE_ID),
                    timeout_sec=_warm_ui_parallel_wait_sec(30.0),
                )
                assert default_state.get("ready") is True, default_state

            before = client.evaluate(page, _READ_THEME_TOKENS, timeout_sec=30.0)
            assert isinstance(before, dict), before
            before_primary = str(before.get("primary") or "").lower()

            click_state = client.evaluate(
                page, _click_preset_snippet(_ROSE_LABELS), timeout_sec=30.0
            )
            assert isinstance(click_state, dict), click_state
            assert click_state.get("ok") is True, click_state

            after = wait_for_state(
                client,
                page,
                _wait_profile_snippet(_ROSE_PROFILE_ID, primary=_ROSE_PRIMARY_LIGHT),
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            )
            assert after.get("ready") is True, after
            after_primary = str(after.get("primary") or "").lower()
            assert after_primary != before_primary, {"before": before, "after": after}
        finally:
            # Best-effort cleanup: leave the shared workspace on the official
            # default for parallel sessions. The click alone is fire-and-forget;
            # wait for the persisted profile to flip back (capped, never fails
            # the test). If the restore fails, the next run's baseline reset
            # still keeps this test idempotent.
            try:
                client.evaluate(
                    page,
                    _click_preset_snippet(_OFFICIAL_DEFAULT_LABELS),
                    timeout_sec=20.0,
                )
                wait_for_state(
                    client,
                    page,
                    _wait_profile_snippet(_OFFICIAL_DEFAULT_PROFILE_ID),
                    timeout_sec=_warm_ui_parallel_wait_sec(20.0),
                )
            except Exception:
                pass
