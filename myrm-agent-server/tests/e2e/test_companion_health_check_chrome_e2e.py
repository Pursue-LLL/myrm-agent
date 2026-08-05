"""Chrome E2E: companion health check opens Pet Palette and expands doctor panel."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_ui_url,
    open_mcp_page,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_OPEN_HEALTH_CHECK_JS = """(() => {
  const bridge = window.__MYRM_E2E_COMPANION__;
  if (!bridge?.openHealthCheck) {
    return { ok: false, err: 'missing_companion_bridge' };
  }
  bridge.openHealthCheck();
  return { ok: true };
})()"""

_CLOSE_PALETTE_JS = """(() => {
  const dialog = document.querySelector('[data-testid="pet-palette-dialog"]')?.closest('[role="dialog"]');
  const closeButton = dialog
    ? Array.from(dialog.querySelectorAll('button')).find((node) => {
        const label = (node.getAttribute('aria-label') || node.textContent || '').trim();
        return label === 'Close' || label === '关闭';
      })
    : null;
  if (closeButton) {
    closeButton.click();
  } else {
    window.__MYRM_E2E_COMPANION__?.closePetPaletteForE2e?.();
  }
  return { ok: true, closed: Boolean(closeButton) };
})()"""

_HEALTH_CHECK_UI_STATE = """(() => {
  const palette = document.querySelector('[data-testid="pet-palette-dialog"]');
  const dialog = palette?.closest('[role="dialog"]');
  const paletteOpen =
    Boolean(palette) &&
    (dialog?.getAttribute('data-state') === 'open' || palette.offsetParent !== null);
  const doctor = document.querySelector('[data-testid="companion-pet-doctor"]');
  const doctorBody = doctor?.querySelector('.border-t');
  const bridgeState = window.__MYRM_E2E_COMPANION__?.getHealthCheckState?.() ?? {};
  return {
    ready:
      paletteOpen &&
      Boolean(doctor) &&
      Boolean(doctorBody) &&
      bridgeState.petPaletteOpen === true,
    hasPalette: Boolean(palette),
    paletteVisible: paletteOpen,
    hasDoctor: Boolean(doctor),
    doctorExpanded: Boolean(doctorBody),
    bridgeState,
  };
})()"""

_SPRITE_ERROR_HEALTH_CHECK_JS = """(() => {
  const bridge = window.__MYRM_E2E_COMPANION__;
  if (!bridge?.prepareBrokenSpriteForE2e) {
    return { ok: false, err: 'missing_companion_bridge' };
  }
  bridge.prepareBrokenSpriteForE2e();
  return { ok: true };
})()"""

_CLICK_SPRITE_HEALTH_CHECK_JS = """(() => {
  const labels = ['Health check', '健康检查'];
  const button = Array.from(document.querySelectorAll('button')).find((node) => {
    const text = (node.textContent || '').trim();
    return labels.some((label) => text === label);
  });
  if (!button) {
    return { ok: false, err: 'sprite_health_check_button_missing' };
  }
  button.click();
  return { ok: true };
})()"""

_SPRITE_ERROR_CTA_READY_JS = """(() => {
  const labels = ['Health check', '健康检查'];
  const button = Array.from(document.querySelectorAll('button')).find((node) => {
    const text = (node.textContent || '').trim();
    return labels.some((label) => text === label);
  });
  return { ready: Boolean(button), hasButton: Boolean(button) };
})()"""

_COMPANION_BRIDGE_READY_JS = """(() => ({
  ready: typeof window.__MYRM_E2E_COMPANION__?.openHealthCheck === 'function',
}))()"""


def _assert_health_check_ui(client, page) -> None:
    state = wait_for_state(
        client,
        page,
        _HEALTH_CHECK_UI_STATE,
        timeout_sec=_warm_ui_parallel_wait_sec(120.0),
    )
    assert state.get("ready") is True, state
    assert state.get("paletteVisible") is True, state
    assert state.get("doctorExpanded") is True, state


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_companion_health_check_store_and_sprite_error_paths() -> None:
    """Store health-check and broken-sprite CTA both open Pet Palette + doctor."""
    ui_url = get_e2e_ui_url()

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=f"{ui_url}/")
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=f"{ui_url}/",
        )
        client.navigate(page, f"{ui_url}/", timeout_ms=90_000)
        dismiss_blocking_modals(client, page)

        bridge_ready: dict[str, object] = {}
        for attempt in range(3):
            try:
                bridge_ready = wait_for_state(
                    client,
                    page,
                    _COMPANION_BRIDGE_READY_JS,
                    timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                )
                if bridge_ready.get("ready") is True:
                    break
            except AssertionError:
                if attempt >= 2:
                    raise
            if attempt < 2:
                reload_mcp_page(client, page, target_url=f"{ui_url}/", timeout_ms=90_000)
                dismiss_blocking_modals(client, page)

        assert bridge_ready.get("ready") is True, bridge_ready

        opened = client.evaluate(page, _OPEN_HEALTH_CHECK_JS)
        assert opened.get("ok") is True, opened
        _assert_health_check_ui(client, page)

        client.evaluate(page, _CLOSE_PALETTE_JS)

        prepared = client.evaluate(page, _SPRITE_ERROR_HEALTH_CHECK_JS)
        assert prepared.get("ok") is True, prepared

        sprite_ready = wait_for_state(
            client,
            page,
            _SPRITE_ERROR_CTA_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert sprite_ready.get("ready") is True, sprite_ready

        clicked = client.evaluate(page, _CLICK_SPRITE_HEALTH_CHECK_JS)
        assert clicked.get("ok") is True, clicked
        _assert_health_check_ui(client, page)
