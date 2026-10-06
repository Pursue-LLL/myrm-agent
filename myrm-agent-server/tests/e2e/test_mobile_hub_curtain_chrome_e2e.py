"""Chrome E2E: mobile hub workstation-curtain status contract and shield badge.

Verifies the privacy-curtain wiring end to end against the LIVE backend and a
real Chrome session (no mock, no fake payload):

  1. contract — ``GET /api/v1/remote-access/mobile/sessions`` ships a ``curtain``
     block carrying boolean ``available`` / ``active``;
  2. render — the ``/mobile`` hub paints in real Chrome;
  3. consistency — the shield badge is present iff the contract reports an
     engaged curtain. The badge is the hub's only semantic
     ``<output aria-live="polite">`` (see ``MobileSessionHub``), so the probe is
     locale-independent, and a desktop-only capability never fakes protection
     on a non-desktop host.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)

# The hub shell plus the sole <output aria-live="polite"> (the curtain badge).
_HUB_PROBE_JS = """(() => {
  const badges = document.querySelectorAll('output[aria-live="polite"]');
  const body = document.body;
  return {
    pathname: window.location.pathname,
    hasMain: !!document.querySelector('main'),
    bodyTextLength: body ? body.innerText.length : 0,
    badgeCount: badges.length,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_mobile_hub_curtain_status_chrome_e2e() -> None:
    """Live contract + real hub render agree on the curtain shield badge."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    payload = http_json("GET", f"{api_url}/api/v1/remote-access/mobile/sessions")
    assert isinstance(payload, dict), f"unexpected hub payload: {payload!r}"
    data = payload.get("data")
    assert isinstance(data, dict), f"hub payload missing data envelope: {payload!r}"

    curtain = data.get("curtain")
    assert isinstance(curtain, dict), f"mobile hub must carry curtain status: {data.keys()}"
    available = curtain.get("available")
    active = curtain.get("active")
    assert isinstance(available, bool), curtain
    assert isinstance(active, bool), curtain

    warm_ui_route("/mobile")
    with open_mcp_page(f"{ui_url}/mobile", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=f"{ui_url}/mobile")
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=f"{ui_url}/mobile",
        )
        probe = client.evaluate(page, _HUB_PROBE_JS)

    assert probe.get("pathname") == "/mobile", probe
    assert probe.get("hasMain") is True, f"mobile hub shell did not render: {probe}"
    assert probe.get("bodyTextLength", 0) > 0, f"mobile hub rendered empty: {probe}"

    # Badge shows only for an available, engaged curtain (MobileSessionHub rule).
    expected_badges = 1 if (available and active) else 0
    assert probe.get("badgeCount") == expected_badges, f"curtain badge mismatch: curtain={curtain} probe={probe}"
