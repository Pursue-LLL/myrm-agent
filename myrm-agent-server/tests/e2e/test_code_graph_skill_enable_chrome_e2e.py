"""Chrome MCP E2E: switching ``repo-call-graph`` on in Settings asks for its ``file_read`` permission first.

Real user flows on /settings/skills: flip the skill's switch, see the permission approval dialog name the permission, then
approve it, approve it through a permission template, or deny it. The flows run against the real backend, so the enable
endpoint has to answer with the pending approval instead of an error, and the grants have to be stored, or not stored.

The model is not involved: ``test_code_graph_callers_live_chrome_e2e.py`` covers the turn that calls ``code_graph_tool``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
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
# The "data analysis" template covers the permission the skill asks for and one more, so the grants tell it apart from
# approving the permission itself.
TEMPLATE_LABEL = r"\(file_read, code_interpreter\)"
TEMPLATE_PERMISSIONS = ["code_interpreter", "file_read"]
SKILLS_URL = f"/settings/skills?search={SKILL_ID}"
PERMISSION_LABEL = r"Read File|读取文件"
ENABLED_WITHIN_SECONDS = 30.0
SETTLE_SECONDS = 1.5
RECHECK_WITHIN_SECONDS = 10.0

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

_SWITCH_ON_JS = _probe(
    """
  return {
    ready: !!skillSwitch && skillSwitch.getAttribute('aria-checked') === 'true',
    switchFound: !!skillSwitch,
    checked: skillSwitch ? skillSwitch.getAttribute('aria-checked') : null,
  };
"""
)


def _flip_switch_js(flag: str) -> str:
    """Click the skill's switch once (``flag`` stops a repeated poll from flipping it back); ready when the dialog names the permission."""
    return _probe(
        """
  if (skillSwitch && !window.__FLAG__) {
    window.__FLAG__ = true;
    skillSwitch.click();
  }
  const text = dialog ? dialog.innerText : '';
  return {
    ready: !!dialog && text.includes('__SKILL__') && /__PERMISSION_LABEL__/.test(text),
    dialogText: text.slice(0, 600),
  };
""".replace("__PERMISSION_LABEL__", PERMISSION_LABEL).replace("__FLAG__", flag)
    )


def _dialog_button_js(label: str, flag: str) -> str:
    """Click the dialog button called ``label`` once; ready when the dialog is gone."""
    return _probe(
        """
  const button = dialog
    ? Array.from(dialog.querySelectorAll('button')).find((b) => /^(__LABEL__)$/.test((b.textContent || '').trim()))
    : null;
  if (button && !window.__FLAG__) {
    window.__FLAG__ = true;
    button.click();
  }
  return { ready: !dialog && !!window.__FLAG__, buttonFound: !!button, dialogOpen: !!dialog };
""".replace("__LABEL__", label).replace("__FLAG__", flag)
    )


_OPEN_TEMPLATES_JS = _probe(
    """
  const trigger = dialog ? dialog.querySelector('[role="combobox"]') : null;
  if (trigger && !window.__templatesOpened) {
    window.__templatesOpened = true;
    trigger.click();
  }
  const options = Array.from(document.querySelectorAll('[role="option"]')).map((o) => (o.textContent || '').trim());
  return { ready: options.length > 0, triggerFound: !!trigger, options };
"""
)

_PICK_TEMPLATE_JS = _probe(
    """
  const option = Array.from(document.querySelectorAll('[role="option"]'))
    .find((o) => /__TEMPLATE__/.test((o.textContent || '').trim()));
  if (option && !window.__templatePicked) {
    window.__templatePicked = true;
    option.click();
  }
  const trigger = dialog ? dialog.querySelector('[role="combobox"]') : null;
  const chosen = (trigger?.textContent || '').trim();
  return { ready: !!window.__templatePicked && /__TEMPLATE__/.test(chosen), optionFound: !!option, chosen };
""".replace("__TEMPLATE__", TEMPLATE_LABEL)
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
    return sorted(str(grant["permission"]) for grant in permissions["granted_permissions"])


def _wait_until_enabled() -> None:
    deadline = time.monotonic() + ENABLED_WITHIN_SECONDS
    while SKILL_ID not in _enabled_prebuilt_ids():
        assert time.monotonic() < deadline, f"approving the permission did not enable {SKILL_ID}"
        time.sleep(0.5)


def _expect(client: ChromeMcpClient, page: McpPage, expression: str, timeout_sec: float) -> None:
    state = wait_for_state(client, page, expression, timeout_sec=timeout_sec)
    assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)


def _assert_still_off_and_ungranted() -> None:
    assert SKILL_ID not in _enabled_prebuilt_ids(), "the skill must stay off until the permission is approved"
    assert _granted_permissions() == []


@contextmanager
def _skills_page() -> Iterator[tuple[ChromeMcpClient, McpPage, float]]:
    """The Installed tab narrowed to the skill, which is off with nothing granted; both are put back afterwards."""
    prepare_e2e_ui_session(get_e2e_api_url())
    _assert_still_off_and_ungranted()

    warm_ui_route("/settings")
    warm_ui_route("/settings/skills", timeout_sec=_warm_ui_parallel_wait_sec(180.0))
    try:
        with open_settings_subroute(SKILLS_URL, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            wait = _warm_ui_parallel_wait_sec(90.0)
            _expect(client, page, _SWITCH_OFF_JS, wait)
            yield client, page, wait
    finally:
        http_json("POST", f"{_skill_api()}/disable")
        http_json("POST", f"{_skill_api()}/permissions/revoke", {"permissions": sorted({PERMISSION, *TEMPLATE_PERMISSIONS})})


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_switching_the_skill_on_asks_for_file_read_and_enables_it_once_approved() -> None:
    with _skills_page() as (client, page, wait):
        # The enable request is answered with the pending approval; the dialog opens only once the page has loaded
        # the code that builds it, which takes long on a dev server that compiles on demand.
        _expect(client, page, _flip_switch_js("__codeGraphFlipped"), wait)
        _assert_still_off_and_ungranted()

        _expect(client, page, _dialog_button_js("Approve|批准", "__codeGraphApproved"), wait)
        _wait_until_enabled()
        assert _granted_permissions() == [PERMISSION]

        reload_mcp_page(client, page, target_url=f"{get_e2e_ui_url()}{SKILLS_URL}")
        _expect(client, page, _SWITCH_ON_JS, wait)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_permission_template_covering_file_read_grants_the_template_and_enables_the_skill() -> None:
    with _skills_page() as (client, page, wait):
        _expect(client, page, _flip_switch_js("__codeGraphFlipped"), wait)
        _assert_still_off_and_ungranted()

        _expect(client, page, _OPEN_TEMPLATES_JS, wait)
        _expect(client, page, _PICK_TEMPLATE_JS, wait)
        _assert_still_off_and_ungranted()

        _expect(client, page, _dialog_button_js("Approve|批准", "__codeGraphApproved"), wait)
        _wait_until_enabled()
        assert _granted_permissions() == TEMPLATE_PERMISSIONS

        reload_mcp_page(client, page, target_url=f"{get_e2e_ui_url()}{SKILLS_URL}")
        _expect(client, page, _SWITCH_ON_JS, wait)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_denying_the_permission_keeps_the_skill_off_and_it_is_asked_again() -> None:
    with _skills_page() as (client, page, wait):
        _expect(client, page, _flip_switch_js("__codeGraphFlipped"), wait)
        _expect(client, page, _dialog_button_js("Deny|拒绝", "__codeGraphDenied"), wait)

        # A switch that turns itself on after the dialog closed would show up here.
        time.sleep(SETTLE_SECONDS)
        _expect(client, page, _SWITCH_OFF_JS, RECHECK_WITHIN_SECONDS)
        _assert_still_off_and_ungranted()

        _expect(client, page, _flip_switch_js("__codeGraphFlippedAgain"), wait)
        _assert_still_off_and_ungranted()
