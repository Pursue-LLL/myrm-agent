"""READ lane Chrome E2E: Discover install → catalog enable (SAL SSOT)."""

from __future__ import annotations

import json
import time
import urllib.parse

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
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


_MIRROR_PANEL_READY_JS = """(() => {
  const mirrorPanel = Array.from(document.querySelectorAll('.rounded-md.border')).find((panel) =>
    /Skill market mirror|技能市场镜像|技能市場鏡像/i.test(panel.textContent || ''),
  );
  const combobox = mirrorPanel?.querySelector('button[role="combobox"]');
  return {
    ready: !!mirrorPanel && !!combobox,
    hasMirrorPanel: !!mirrorPanel,
    hasCombobox: !!combobox,
  };
})()"""


_OPEN_MIRROR_SELECT_JS = """(() => {
  const mirrorPanel = Array.from(document.querySelectorAll('.rounded-md.border')).find((panel) =>
    /Skill market mirror|技能市场镜像|技能市場鏡像/i.test(panel.textContent || ''),
  );
  const trigger = mirrorPanel?.querySelector('button[role="combobox"]');
  if (!trigger) {
    return { ok: false, reason: 'combobox-missing' };
  }
  trigger.click();
  return { ok: true };
})()"""


_SELECT_CN_MIRROR_JS = """(() => {
  const option = Array.from(document.querySelectorAll('[role="option"]')).find((el) =>
    /China|中国|iFlytek|讯飞/i.test(el.textContent || ''),
  );
  if (!option) {
    return { ok: false, reason: 'cn-option-missing' };
  }
  option.click();
  return { ok: true };
})()"""


_MIRROR_SAVED_TOAST_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  return {
    ready: /Mirror settings saved|镜像设置已保存|鏡像設定已儲存/i.test(bodyText),
  };
})()"""


_SELECT_CUSTOM_MIRROR_JS = """(() => {
  const option = Array.from(document.querySelectorAll('[role="option"]')).find((el) =>
    /Custom|自定义|自訂/i.test(el.textContent || ''),
  );
  if (!option) {
    return { ok: false, reason: 'custom-option-missing' };
  }
  option.click();
  return { ok: true };
})()"""


def _wait_registry_url(api_url: str, expected_url: str, *, timeout_sec: float = 60.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        last = http_json("GET", f"{api_url}/api/v1/skills/config")
        if last.get("clawhub_registry_url") == expected_url:
            return last
        time.sleep(1.0)
    pytest.fail(
        f"Timed out waiting for clawhub_registry_url={expected_url!r}; last={last!r}"
    )


_CUSTOM_INPUT_READY_JS = """(() => {
  const mirrorPanel = Array.from(document.querySelectorAll('.rounded-md.border')).find((panel) =>
    /Skill market mirror|技能市场镜像|技能市場鏡像/i.test(panel.textContent || ''),
  );
  const input = mirrorPanel?.querySelector('input');
  const saveBtn = Array.from(mirrorPanel?.querySelectorAll('button') || []).find((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()),
  );
  return { ready: !!input && !!saveBtn, hasInput: !!input, hasSave: !!saveBtn };
})()"""


_FOCUS_CUSTOM_MIRROR_INPUT_JS = """(() => {
  const mirrorPanel = Array.from(document.querySelectorAll('.rounded-md.border')).find((panel) =>
    /Skill market mirror|技能市场镜像|技能市場鏡像/i.test(panel.textContent || ''),
  );
  const input = mirrorPanel?.querySelector('input');
  if (!input) {
    return { ok: false, reason: 'input-missing' };
  }
  input.focus();
  input.click();
  return { ok: true, focused: document.activeElement === input };
})()"""


_CLICK_CUSTOM_MIRROR_SAVE_JS = """(() => {
  const mirrorPanel = Array.from(document.querySelectorAll('.rounded-md.border')).find((panel) =>
    /Skill market mirror|技能市场镜像|技能市場鏡像/i.test(panel.textContent || ''),
  );
  const saveBtn = Array.from(mirrorPanel?.querySelectorAll('button') || []).find((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()),
  );
  if (!saveBtn || saveBtn.disabled) {
    return { ok: false, reason: 'save-disabled-or-missing', disabled: !!saveBtn?.disabled };
  }
  saveBtn.click();
  return { ok: true };
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


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_discover_prebuilt_install_enables_catalog_without_agent_allowlist() -> None:
    """Discover prebuilt install enables catalog; empty agent.skill_ids stays unchanged."""
    api_url = get_e2e_api_url()

    search_query, skill_id, _skill_name = _find_prebuilt_target(api_url)
    prior_enabled = _disable_prebuilt_for_install(api_url, skill_id)
    _assert_agent_allowlist_untouched(api_url)

    prepare_e2e_ui_session(api_url)
    warm_ui_route("/settings/skills")

    try:
        with open_settings_subroute("/settings/skills") as (client, page):
            wait_for_state(client, page, _DISCOVER_TAB_READY_JS, timeout_sec=90.0)

            submitted = client.evaluate(
                page,
                _search_and_install_js(skill_id),
                timeout_sec=15.0,
            )
            assert isinstance(submitted, dict)
            assert submitted.get("ok") is True, submitted

            wait_for_state(client, page, _results_ready_js(skill_id), timeout_sec=60.0)

            clicked = client.evaluate(
                page,
                _click_prebuilt_install_js(skill_id),
                timeout_sec=15.0,
            )
            assert isinstance(clicked, dict)
            assert clicked.get("ok") is True, clicked

            install_deadline = time.monotonic() + 90.0
            toast_state: dict[str, object] = {"ready": False}
            while time.monotonic() < install_deadline:
                raw_toast = client.evaluate(
                    page, _INSTALL_TOAST_READY_JS, timeout_sec=15.0
                )
                toast_state = raw_toast if isinstance(raw_toast, dict) else {"ready": False}
                if toast_state.get("ready") is True:
                    break
                enabled_check = http_json("GET", f"{api_url}/api/v1/skills/config")
                if skill_id in set(enabled_check.get("enabled_prebuilt_ids") or []):
                    toast_state = {"ready": True, "via": "api-catalog"}
                    break
                time.sleep(1.0)
            assert toast_state.get("ready") is True, toast_state
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
    assert skill_id in enabled_after, f"Expected {skill_id} enabled; got {enabled_after!r}"
    _assert_agent_allowlist_untouched(api_url)


def _restore_registry_url(api_url: str, prior_registry_url: str) -> None:
    http_json(
        "PUT",
        f"{api_url}/api/v1/skills/config",
        {"clawhub_registry_url": prior_registry_url or ""},
    )


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_discover_cn_mirror_select_save_via_ui() -> None:
    """Discover settings: CN mirror select persists via API."""
    api_url = get_e2e_api_url()

    probe = http_json(
        "GET", f"{api_url}/api/v1/skills/discovery/registry-probe?mirror=cn"
    )
    assert probe.get("reachable") is True, probe

    prior_config = http_json("GET", f"{api_url}/api/v1/skills/config")
    prior_registry_url = str(prior_config.get("clawhub_registry_url") or "")

    prepare_e2e_ui_session(api_url)
    warm_ui_route("/settings/skills")

    try:
        with open_settings_subroute("/settings/skills") as (client, page):
            wait_for_state(client, page, _MIRROR_PANEL_READY_JS, timeout_sec=60.0)
            opened = client.evaluate(page, _OPEN_MIRROR_SELECT_JS, timeout_sec=15.0)
            assert isinstance(opened, dict) and opened.get("ok") is True, opened
            selected = client.evaluate(page, _SELECT_CN_MIRROR_JS, timeout_sec=15.0)
            assert isinstance(selected, dict) and selected.get("ok") is True, selected
            mirror_toast = wait_for_state(
                client, page, _MIRROR_SAVED_TOAST_JS, timeout_sec=60.0
            )
            assert mirror_toast.get("ready") is True, mirror_toast
            mirror_config = http_json("GET", f"{api_url}/api/v1/skills/config")
            assert mirror_config.get("clawhub_registry_url") == "https://skill.xfyun.cn"
    finally:
        _restore_registry_url(api_url, prior_registry_url)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_discover_custom_mirror_url_save_via_ui() -> None:
    """Discover settings: Custom URL input + Save persists normalized registry URL."""
    api_url = get_e2e_api_url()

    prior_config = http_json("GET", f"{api_url}/api/v1/skills/config")
    prior_registry_url = str(prior_config.get("clawhub_registry_url") or "")

    prepare_e2e_ui_session(api_url)
    warm_ui_route("/settings/skills")

    custom_url = "https://clawhub.ai"
    expected_custom_stored = ""

    try:
        with open_settings_subroute("/settings/skills") as (client, page):
            wait_for_state(client, page, _MIRROR_PANEL_READY_JS, timeout_sec=60.0)
            opened = client.evaluate(page, _OPEN_MIRROR_SELECT_JS, timeout_sec=15.0)
            assert isinstance(opened, dict) and opened.get("ok") is True, opened
            picked_custom = client.evaluate(page, _SELECT_CUSTOM_MIRROR_JS, timeout_sec=15.0)
            assert isinstance(picked_custom, dict) and picked_custom.get("ok") is True, picked_custom
            wait_for_state(client, page, _CUSTOM_INPUT_READY_JS, timeout_sec=30.0)
            focused = client.evaluate(
                page, _FOCUS_CUSTOM_MIRROR_INPUT_JS, timeout_sec=15.0
            )
            assert isinstance(focused, dict) and focused.get("ok") is True, focused
            client.type_text(page, custom_url)
            save_ready = wait_for_state(
                client,
                page,
                """(() => {
  const mirrorPanel = Array.from(document.querySelectorAll('.rounded-md.border')).find((panel) =>
    /Skill market mirror|技能市场镜像|技能市場鏡像/i.test(panel.textContent || ''),
  );
  const saveBtn = Array.from(mirrorPanel?.querySelectorAll('button') || []).find((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()),
  );
  return { ready: !!saveBtn && !saveBtn.disabled };
})()""",
                timeout_sec=15.0,
            )
            assert save_ready.get("ready") is True, save_ready
            clicked_save = client.evaluate(
                page, _CLICK_CUSTOM_MIRROR_SAVE_JS, timeout_sec=15.0
            )
            assert isinstance(clicked_save, dict) and clicked_save.get("ok") is True, clicked_save
            custom_config = _wait_registry_url(
                api_url, expected_custom_stored, timeout_sec=60.0
            )
            assert custom_config.get("clawhub_registry_url") == expected_custom_stored
    finally:
        _restore_registry_url(api_url, prior_registry_url)
