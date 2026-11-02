"""Chrome MCP E2E: switching ``repo-call-graph`` on in Settings asks for its ``file_read`` permission, then enables it.

Real user flow on /settings/skills: flip the skill's switch, see the permission approval dialog name the permission,
approve it, and find the skill switched on after the page is loaded again. The flow runs against the real backend, so the
enable endpoint has to answer with the pending approval instead of an error, and the grant has to be stored.

The model is not involved: ``test_code_graph_callers_live_chrome_e2e.py`` covers the turn that calls ``code_graph_tool``.
"""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

SKILL_ID = "repo-call-graph"
PERMISSION = "file_read"
SKILLS_URL = f"/settings/skills?search={SKILL_ID}"
PERMISSION_LABEL = r"Read File|读取文件"
ENABLED_WITHIN_SECONDS = 30.0

# ``?search=`` opens the Installed tab with the list narrowed to the skill. The skill's switch is the one in the nearest
# ancestor that names the skill and holds no other switch: the card.
_FIND_SWITCH_JS = """
  const switches = Array.from(document.querySelectorAll('[role="switch"]'));
  const skillSwitch = switches.find((sw) => {
    for (let node = sw.parentElement, depth = 0; node && depth < 8; node = node.parentElement, depth += 1) {
      if ((node.innerText || '').includes('__SKILL__')) return node.querySelectorAll('[role="switch"]').length === 1;
    }
    return false;
  });
  const dialog = document.querySelector('[role="dialog"]');
"""


def _probe(body: str) -> str:
    return ("(() => {" + _FIND_SWITCH_JS + body + "})()").replace("__SKILL__", SKILL_ID)


_SWITCH_OFF_JS = _probe(
    """
  return {
    ready: !!skillSwitch && skillSwitch.getAttribute('aria-checked') === 'false',
    switchFound: !!skillSwitch,
    switchCount: switches.length,
    selectedTab: (document.querySelector('[role="tab"][aria-selected="true"]')?.textContent || '').trim(),
  };
"""
)

# Flipping the switch is guarded by a window flag so that a repeated poll does not flip it back.
_FLIP_SWITCH_JS = _probe(
    """
  if (skillSwitch && !window.__codeGraphSwitchFlipped) {
    window.__codeGraphSwitchFlipped = true;
    skillSwitch.click();
  }
  const text = dialog ? dialog.innerText : '';
  return {
    ready: !!dialog && text.includes('__SKILL__') && /__PERMISSION_LABEL__/.test(text),
    dialogText: text.slice(0, 600),
  };
""".replace("__PERMISSION_LABEL__", PERMISSION_LABEL)
)

_APPROVE_JS = _probe(
    """
  const approve = dialog
    ? Array.from(dialog.querySelectorAll('button')).find((b) => /^(Approve|批准)$/.test((b.textContent || '').trim()))
    : null;
  if (approve && !window.__codeGraphApproved) {
    window.__codeGraphApproved = true;
    approve.click();
  }
  return { ready: !dialog && !!window.__codeGraphApproved, approveFound: !!approve, dialogOpen: !!dialog };
"""
)

_SWITCH_ON_JS = _probe(
    """
  return {
    ready: !!skillSwitch && skillSwitch.getAttribute('aria-checked') === 'true',
    switchFound: !!skillSwitch,
    checked: skillSwitch ? skillSwitch.getAttribute('aria-checked') : null,
  };
"""
)


def _skill_api() -> str:
    return f"{get_e2e_api_url()}/api/v1/skills/{SKILL_ID}"


def _enabled_prebuilt_ids() -> list[str]:
    config = http_json("GET", f"{get_e2e_api_url()}/api/v1/skills/config")
    assert isinstance(config, dict)
    return [str(skill_id) for skill_id in config["enabled_prebuilt_ids"]]


def _granted_permissions() -> list[str]:
    permissions = http_json("GET", f"{_skill_api()}/permissions")
    assert isinstance(permissions, dict)
    return [str(grant["permission"]) for grant in permissions["granted_permissions"]]


def _wait_until_enabled() -> None:
    deadline = time.monotonic() + ENABLED_WITHIN_SECONDS
    while SKILL_ID not in _enabled_prebuilt_ids():
        assert time.monotonic() < deadline, f"approving the permission did not enable {SKILL_ID}"
        time.sleep(0.5)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_switching_the_skill_on_asks_for_file_read_and_enables_it_once_approved() -> None:
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    assert SKILL_ID not in _enabled_prebuilt_ids()
    assert _granted_permissions() == []

    warm_ui_route("/settings")
    warm_ui_route("/settings/skills", timeout_sec=_warm_ui_parallel_wait_sec(180.0))
    try:
        with open_settings_subroute(SKILLS_URL, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            wait = _warm_ui_parallel_wait_sec(90.0)

            off = wait_for_state(client, page, _SWITCH_OFF_JS, timeout_sec=wait)
            assert off.get("ready") is True, json.dumps(off, indent=2, ensure_ascii=False)

            # The enable request is answered with the pending approval; the dialog opens only once the page has loaded
            # the code that builds it, which takes long on a dev server that compiles on demand.
            asked = wait_for_state(client, page, _FLIP_SWITCH_JS, timeout_sec=wait)
            assert asked.get("ready") is True, json.dumps(asked, indent=2, ensure_ascii=False)
            assert SKILL_ID not in _enabled_prebuilt_ids(), "the skill must stay off until the permission is approved"
            assert _granted_permissions() == []

            approved = wait_for_state(client, page, _APPROVE_JS, timeout_sec=wait)
            assert approved.get("ready") is True, json.dumps(approved, indent=2, ensure_ascii=False)
            _wait_until_enabled()
            assert _granted_permissions() == [PERMISSION]

            reload_mcp_page(client, page, target_url=f"{get_e2e_ui_url()}{SKILLS_URL}")
            on = wait_for_state(client, page, _SWITCH_ON_JS, timeout_sec=wait)
            assert on.get("ready") is True, json.dumps(on, indent=2, ensure_ascii=False)
    finally:
        http_json("POST", f"{_skill_api()}/disable")
        http_json("POST", f"{_skill_api()}/permissions/revoke", {"permissions": [PERMISSION]})
