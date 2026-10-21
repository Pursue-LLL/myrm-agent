"""Chrome E2E: Discover install toast undo restores pre-replace SKILL.md (SCC)."""

from __future__ import annotations

import json
import time
import urllib.request

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
  const discoverTab = Array.from(document.querySelectorAll('[role="tab"]')).find((el) =>
    /Discover|发现/i.test(el.textContent || ''),
  );
  if (discoverTab && discoverTab.getAttribute('aria-selected') !== 'true') {
    discoverTab.click();
  }
  const searchInput = Array.from(document.querySelectorAll('input')).find((el) =>
    /Search skills|搜索技能/i.test(el.getAttribute('placeholder') || ''),
  );
  return { ready: !!searchInput && !!window.__MYRM_E2E_SKILLS_DISCOVER__?.showInstallResultToast };
})()"""


def _show_replace_toast_js(seed: dict[str, object]) -> str:
    payload = json.dumps(
        {
            "skillName": seed["skill_name"],
            "response": {
                "success": True,
                "skill_id": seed["skill_id"],
                "pre_replace_batch_id": seed["pre_replace_batch_id"],
                "snapshot_truncated": seed.get("snapshot_truncated", False),
            },
            "marketUpdate": True,
        },
        ensure_ascii=False,
    )
    return f"""(() => {{
  const bridge = window.__MYRM_E2E_SKILLS_DISCOVER__;
  if (!bridge?.showInstallResultToast) return {{ ok: false, err: 'missing-skills-bridge' }};
  bridge.showInstallResultToast({payload});
  return {{ ok: true }};
}})()"""


_TOAST_UNDO_READY_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const undo = buttons.find((btn) =>
    /Undo last update|Restore previous|撤销上次|直近の更新を元に戻す|Letztes Update rückgängig/i.test(
      (btn.textContent || '').trim(),
    ),
  );
  return { ready: !!undo, label: undo?.textContent?.trim() ?? null };
})()"""


def _click_toast_undo_js() -> str:
    return """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const undo = buttons.find((btn) =>
    /Undo last update|Restore previous|撤销上次|直近の更新を元に戻す|Letztes Update rückgängig/i.test(
      (btn.textContent || '').trim(),
    ),
  );
  if (!undo) return { ok: false, err: 'missing-undo-button' };
  undo.click();
  return { ok: true };
})()"""


def _fetch_skill_md(api_url: str, skill_id: str) -> str:
    url = f"{api_url}/api/v1/skills/{skill_id}/files/SKILL.md"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        return response.read().decode("utf-8")


_RESTORE_SUCCESS_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  return {
    ready: /Restored previous|restored|已恢复|已恢復|wiederhergestellt|復元/i.test(bodyText),
    sample: bodyText.slice(0, 400),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_discover_replace_toast_undo_restores_skill_md() -> None:
    """Real replace batch + Discover toast undo rolls back SKILL.md via rollback API."""
    api_url = get_e2e_api_url()
    seed = http_json("POST", f"{api_url}/api/v1/skills/test/seed-scc-market-replace")
    skill_id = str(seed["skill_id"])
    marker_v1 = str(seed["marker_v1"])
    marker_v2 = str(seed["marker_v2"])

    after_seed = _fetch_skill_md(api_url, skill_id)
    assert marker_v2 in after_seed

    prepare_e2e_ui_session(api_url)
    warm_ui_route("/settings/skills")

    with open_settings_subroute("/settings/skills") as (client, page):
        wait_for_state(client, page, _DISCOVER_TAB_READY_JS, timeout_sec=90.0)
        shown = client.evaluate(page, _show_replace_toast_js(seed), timeout_sec=15.0)
        assert isinstance(shown, dict) and shown.get("ok") is True, shown

        undo_ready = wait_for_state(client, page, _TOAST_UNDO_READY_JS, timeout_sec=30.0)
        assert undo_ready.get("ready") is True, undo_ready

        clicked = client.evaluate(page, _click_toast_undo_js(), timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        deadline = time.monotonic() + 45.0
        restored = False
        while time.monotonic() < deadline:
            content = _fetch_skill_md(api_url, skill_id)
            if marker_v1 in content and marker_v2 not in content:
                restored = True
                break
            time.sleep(0.5)
        assert restored, "Rollback did not restore v1 marker on SKILL.md"

        success_state = wait_for_state(client, page, _RESTORE_SUCCESS_JS, timeout_sec=30.0)
        assert success_state.get("ready") is True, success_state
