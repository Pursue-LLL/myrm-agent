"""READ lane Chrome E2E: Discover install → catalog enable (SAL SSOT)."""

from __future__ import annotations

import json
import urllib.parse

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISCOVER_TAB_READY_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  const searchInput = Array.from(document.querySelectorAll('input')).find((el) =>
    /Search skills|搜索技能/i.test(el.getAttribute('placeholder') || ''),
  );
  const discoverTab = Array.from(document.querySelectorAll('[role="tab"]')).find((el) =>
    /Discover|发现/i.test(el.textContent || ''),
  );
  if (discoverTab && discoverTab.getAttribute('aria-selected') !== 'true') {
    discoverTab.click();
  }
  return {
    ready:
      !!searchInput &&
      (/Discover|发现/i.test(bodyText) || !!discoverTab),
    hasSearchInput: !!searchInput,
  };
})()"""


def _search_and_install_js(query: str) -> str:
    q = json.dumps(query)
    return f"""(() => {{
  const query = {q};
  const searchInput = Array.from(document.querySelectorAll('input')).find((el) =>
    /Search skills|搜索技能/i.test(el.getAttribute('placeholder') || ''),
  );
  if (!searchInput) {{
    return {{ ok: false, reason: 'missing-search-input' }};
  }}
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value',
  )?.set;
  if (!setter) {{
    return {{ ok: false, reason: 'input-setter-missing' }};
  }}
  setter.call(searchInput, query);
  searchInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
  searchInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
  searchInput.dispatchEvent(
    new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}),
  );
  return {{ ok: true, submitted: true, query }};
}})()"""


def _results_ready_js(skill_id: str) -> str:
    sid = json.dumps(skill_id)
    return f"""(() => {{
  const skillId = {sid};
  const searching = !!document.querySelector('input[placeholder*="Search skills"], input[placeholder*="搜索技能"]')
    ?.parentElement?.querySelector('.animate-spin');
  const cards = Array.from(document.querySelectorAll('.rounded-lg.border.bg-card'));
  const target = cards.find((card) => (card.textContent || '').includes(skillId));
  return {{
    ready: !searching && !!target,
    searching: !!searching,
    cardCount: cards.length,
    hasTarget: !!target,
  }};
}})()"""


def _click_prebuilt_install_js(skill_id: str) -> str:
    sid = json.dumps(skill_id)
    return f"""(() => {{
  const skillId = {sid};
  const cards = Array.from(document.querySelectorAll('.rounded-lg.border.bg-card'));
  const targetCard = cards.find((card) => (card.textContent || '').includes(skillId));
  if (!targetCard) {{
    return {{ ok: false, reason: 'skill-card-missing', cardCount: cards.length }};
  }}
  const installBtn = Array.from(targetCard.querySelectorAll('button')).find((btn) =>
    /^(Install|安装)$/i.test((btn.textContent || '').trim()),
  );
  if (!installBtn) {{
    return {{ ok: false, reason: 'install-button-missing' }};
  }}
  installBtn.click();
  return {{ ok: true, clicked: true }};
}})()"""


_INSTALL_TOAST_READY_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  const toastMatch =
    /Installed and enabled|已安装并启用|已安裝並啟用/i.test(bodyText);
  const installedBadge = Array.from(document.querySelectorAll('button')).some((btn) =>
    /^(Installed|已安装|已安裝)$/i.test((btn.textContent || '').trim()),
  );
  return { ready: toastMatch || installedBadge, toastMatch, installedBadge };
})()"""


def _find_prebuilt_target(api_url: str) -> tuple[str, str, str]:
    """Return (search_query, skill_id, skill_name) for a prebuilt skill."""
    for query in ("systematic", "code review", "debugging"):
        encoded = urllib.parse.quote(query)
        search = http_json(
            "GET",
            f"{api_url}/api/v1/skills/discovery/search?q={encoded}&limit=30",
        )
        results = search.get("results") or []
        for item in results:
            if item.get("source") != "prebuilt":
                continue
            skill_id = str(item.get("id") or "")
            skill_name = str(item.get("name") or skill_id)
            if skill_id:
                return query, skill_id, skill_name

    pytest.fail("No prebuilt skill found in discovery search for SAL Discover E2E")


def _disable_prebuilt_for_install(api_url: str, skill_id: str) -> list[str]:
    """Remove skill_id from catalog enable list so UI install can re-enable it."""
    config = http_json("GET", f"{api_url}/api/v1/skills/config")
    enabled = list(config.get("enabled_prebuilt_ids") or [])
    if skill_id not in enabled:
        return enabled
    updated = [item for item in enabled if item != skill_id]
    http_json(
        "PUT",
        f"{api_url}/api/v1/skills/config",
        {"enabled_prebuilt_ids": updated},
    )
    return enabled


def _assert_agent_allowlist_untouched(api_url: str) -> None:
    agent = http_json("GET", f"{api_url}/api/v1/user-agents/builtin-general")
    data = agent.get("data") if isinstance(agent.get("data"), dict) else agent
    skill_ids = data.get("skill_ids") if isinstance(data, dict) else None
    assert (
        skill_ids == [] or skill_ids is None
    ), f"SAL must not write agent.skill_ids; got {skill_ids!r}"


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_discover_prebuilt_install_enables_catalog_without_agent_allowlist() -> None:
    """Discover tab: install prebuilt → toast + catalog enable; agent.skill_ids stays empty."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    probe = http_json(
        "GET", f"{api_url}/api/v1/skills/discovery/registry-probe?mirror=cn"
    )
    assert isinstance(probe, dict)
    assert (
        probe.get("reachable") is True
    ), f"CN registry probe must be reachable: {probe!r}"

    search_query, skill_id, skill_name = _find_prebuilt_target(api_url)
    prior_enabled = _disable_prebuilt_for_install(api_url, skill_id)
    _assert_agent_allowlist_untouched(api_url)

    prepare_e2e_ui_session(api_url)
    warm_ui_route("/settings/skills")

    try:
        with open_mcp_page(f"{ui_url}/settings/skills") as (client, page):
            wait_for_state(client, page, _DISCOVER_TAB_READY_JS, timeout_sec=90.0)

            submitted = client.evaluate(
                page,
                _search_and_install_js(skill_id),
                timeout_sec=15.0,
            )
            assert isinstance(submitted, dict)
            assert (
                submitted.get("ok") is True
            ), f"Discover search submit failed: {submitted}"

            wait_for_state(client, page, _results_ready_js(skill_id), timeout_sec=60.0)

            clicked = client.evaluate(
                page,
                _click_prebuilt_install_js(skill_id),
                timeout_sec=15.0,
            )
            assert isinstance(clicked, dict)
            assert (
                clicked.get("ok") is True
            ), f"Discover install click failed: {clicked}"

            toast_state = wait_for_state(
                client, page, _INSTALL_TOAST_READY_JS, timeout_sec=60.0
            )
            assert (
                toast_state.get("ready") is True
            ), f"Expected install+enable toast or Installed badge: {toast_state}"
    finally:
        config_check = http_json("GET", f"{api_url}/api/v1/skills/config")
        enabled_now = set(config_check.get("enabled_prebuilt_ids") or [])
        if skill_id not in enabled_now:
            http_json(
                "PUT",
                f"{api_url}/api/v1/skills/config",
                {"enabled_prebuilt_ids": prior_enabled},
            )

    config_after = http_json("GET", f"{api_url}/api/v1/skills/config")
    enabled_after = set(config_after.get("enabled_prebuilt_ids") or [])
    assert (
        skill_id in enabled_after
    ), f"Expected {skill_id} in enabled_prebuilt_ids; got {enabled_after!r}"
    _assert_agent_allowlist_untouched(api_url)
