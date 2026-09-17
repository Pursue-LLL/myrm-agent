"""Chrome E2E: user adds a pre-trusted desktop app in the agent Capabilities tab and it persists.

Covers the CronLegacyDesktopUnattendedTrustLatchPack front-end chain end to end:
  T1 - Settings > Agents opens the agent editor for a seeded agent.
  T2 - The Capabilities tab exposes the pre-trusted desktop apps section.
  T3 - Typing an app name and clicking Add, then Save, persists
       trusted_desktop_apps through PUT (asserted via GET API).
  T4 - Cleanup removes the seeded agent.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_EDIT_URL = "/settings/agents?agentId="

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_HEADING_RE = "/Pre-trusted|预信任|預信任|事前承認|사전 승인|Vorab genehmigte/"
_ADD_RE = "/^(Add|添加|新增|追加|추가|Hinzufügen)$/"

_SECTION_JS = """(() => {
  const tab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  const bodyLength = (document.body?.innerText || '').length;
  if (!tab) {
    return { ready: false, reason: 'no-capabilities-tab', bodyLength };
  }
  tab.click();
  return new Promise(resolve => setTimeout(() => {
    const headings = Array.from(document.querySelectorAll('h4'));
    const heading = headings.find((el) => HEADING_RE_PLACEHOLDER.test(el.textContent || ''));
    if (!heading) {
      return resolve({ ready: false, reason: 'no-trusted-apps-heading', bodyLength });
    }
    const card = heading.closest('div.rounded-xl') || heading.parentElement;
    const input = card ? card.querySelector('input[list]') : null;
    resolve({ ready: !!input, bodyLength });
  }, 300));
})()""".replace("HEADING_RE_PLACEHOLDER", _HEADING_RE)


def _add_app_js(app_name: str) -> str:
    return f"""(() => {{
      const headings = Array.from(document.querySelectorAll('h4'));
      const heading = headings.find((el) => {_HEADING_RE}.test(el.textContent || ''));
      if (!heading) return {{ ok: false, reason: 'no-heading' }};
      const card = heading.closest('div.rounded-xl') || heading.parentElement;
      const input = card ? card.querySelector('input[list]') : null;
      if (!input) return {{ ok: false, reason: 'no-input' }};
      const setter = Object.getOwnPropertyDescriptor(
        Object.getPrototypeOf(input), 'value',
      );
      setter.set.call(input, {json.dumps(app_name)});
      input.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: {json.dumps(app_name)} }}));
      input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      const addBtn = card ? Array.from(card.querySelectorAll('button')).find((b) =>
        {_ADD_RE}.test((b.textContent || '').trim()) && !b.disabled,
      ) : null;
      if (!addBtn) return {{ ok: false, reason: 'no-add-button' }};
      addBtn.click();
      return new Promise(resolve => setTimeout(() => {{
        const section = document.querySelector('[data-section="agents"]') || document.body;
        const saveBtn = Array.from(section.querySelectorAll('button')).find((b) =>
          /^(Save|保存|儲存)$/i.test((b.textContent || '').trim()) && b.offsetParent !== null,
        );
        resolve({{
          ok: true,
          saveDisabled: saveBtn ? saveBtn.disabled : null,
          tagPresent: (card.textContent || '').includes({json.dumps(app_name)}),
        }});
      }}, 300));
    }})()"""


_CLICK_SAVE_JS = """(() => {
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const matches = Array.from(section.querySelectorAll('button')).filter((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()) && btn.offsetParent !== null,
  );
  const save = matches.find((btn) => !btn.disabled);
  const bodyLength = (document.body?.innerText || '').length;
  if (!save) {
    return { ready: false, reason: 'no-enabled-visible-save-button', bodyLength };
  }
  save.click();
  return { ready: true, clicked: (save.textContent || '').trim(), bodyLength };
})()"""

_SAVE_COMPLETE_JS = """(() => {
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const buttons = Array.from(section.querySelectorAll('button'));
  const save = buttons.find((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()) && btn.offsetParent !== null,
  );
  const bodyLength = (document.body?.innerText || '').length;
  if (!save) return { ready: false, reason: 'no-visible-save-button', bodyLength };
  const hasSpinner = !!save.querySelector('.animate-spin');
  return {
    ready: save.disabled && !hasSpinner,
    disabled: save.disabled,
    hasSpinner,
    bodyLength,
  };
})()"""


def _create_agent(api_url: str, *, name: str) -> str:
    resp = http_json("POST", f"{api_url}/api/v1/user-agents", {"name": name})
    data = resp["data"]
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id, json.dumps(data, ensure_ascii=False)
    return agent_id


def _fetch_trusted_apps(api_url: str, agent_id: str) -> object:
    resp = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    return (resp.get("data") or {}).get("trusted_desktop_apps")


def _wait_trusted_apps(api_url: str, agent_id: str, expected: object, *, timeout_sec: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last: object = None
    while time.monotonic() < deadline:
        last = _fetch_trusted_apps(api_url, agent_id)
        if last == expected:
            return
        time.sleep(1.0)
    raise AssertionError(f"trusted_desktop_apps did not persist: expected={expected} last={last}")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_agent_trusted_desktop_apps_add_persists_via_ui() -> None:
    """Pre-trusted desktop app added in the Capabilities tab must persist through the real UI save path."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"trust-e2e-{uuid.uuid4().hex[:8]}"
    agent_id = _create_agent(api_url, name=name)
    try:
        assert _fetch_trusted_apps(api_url, agent_id) in (None, []), "fresh agent must start with no trusted apps"

        warm_ui_route("/settings")
        edit_url = f"{get_e2e_ui_url().rstrip('/')}{_EDIT_URL}{agent_id}"
        with open_settings_subroute(
            edit_url.replace(get_e2e_ui_url().rstrip("/"), ""),
            timeout_ms=120_000,
        ) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            probe = wait_for_state(
                client,
                page,
                _SECTION_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            assert probe.get("ready") is True, json.dumps(probe, indent=2, ensure_ascii=False)

            added = client.evaluate(page, _add_app_js("SAP GUI"), timeout_sec=15.0)
            assert isinstance(added, dict) and added.get("ok") is True, added
            assert added.get("tagPresent") is True, added
            assert added.get("saveDisabled") is False, (
                f"React state must update so the agent Save button unlocks ({added})"
            )

            clicked = wait_for_state(
                client,
                page,
                _CLICK_SAVE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(20.0),
            )
            assert isinstance(clicked, dict) and clicked.get("ready") is True, clicked

            saved = wait_for_state(
                client,
                page,
                _SAVE_COMPLETE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(30.0),
            )
            assert saved.get("ready") is True, json.dumps(saved, indent=2, ensure_ascii=False)

        _wait_trusted_apps(api_url, agent_id, expected=[{"name": "SAP GUI"}])
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
