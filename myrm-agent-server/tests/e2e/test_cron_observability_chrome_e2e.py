"""Chrome E2E: Cron observability UI (#21 frontend delivery).

Single-session anti-mux (READ×1): one attach covers all scenarios — badge,
CreateDialog live preview, and chat-page banner visibility (absent=green, present=yellow/red).
Parallel E2E: do NOT split into per-scenario tests (each would re-attach).
Run: `./myrm test -m chrome_e2e tests/e2e/test_cron_observability_chrome_e2e.py`
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    navigate_mcp_page,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_SCHEDULER_BADGE_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasBadge =
    /Scheduler Running|Scheduler Degraded|Scheduler Stopped|调度器运行中|调度器异常|调度器已停止|排程器/.test(text);
  return { ready: hasBadge, sample: text.slice(0, 300) };
})()"""

_OPEN_CREATE_DIALOG_JS = """(() => {
  const btn = document.querySelector('[data-testid="cron-create-job-button"]')
    || Array.from(document.querySelectorAll('button')).find((el) =>
      /(Create|创建|建立|作成|Erstellen)/i.test((el.textContent || '').trim()),
    );
  if (!btn) {
    const all = Array.from(document.querySelectorAll('button')).map((el) => (el.textContent || '').trim());
    return { ready: false, reason: 'no-create-button', buttons: all.slice(0, 20) };
  }
  btn.click();
  return { ready: true, clicked: true };
})()"""

_CREATE_DIALOG_READY_JS = """(() => {
  const customBtn = document.querySelector('[data-testid="cron-create-mode-custom"]');
  const templateBtn = document.querySelector('[data-testid="cron-create-mode-template"]');
  if (customBtn && templateBtn) {
    return { ready: true };
  }
  const text = document.body?.innerText || '';
  const hasCustom = /(Custom|自定义|自訂)/i.test(text);
  const hasTemplate = /(From Template|从模板|テンプレート|模板)/i.test(text);
  return { ready: hasCustom && hasTemplate, text: text.slice(0, 400) };
})()"""

_SWITCH_CUSTOM_TAB_JS = """(() => {
  const tab = document.querySelector('[data-testid="cron-create-mode-custom"]')
    || Array.from(document.querySelectorAll('button')).find((el) =>
      /(Custom|自定义|自訂)/i.test((el.textContent || '').trim()),
    );
  if (!tab) {
    return { ready: false, reason: 'no-custom-tab' };
  }
  tab.click();
  return { ready: true };
})()"""


def _set_cron_expr_js(expr: str) -> str:
    return f"""(() => {{
      const input = document.querySelector('input.font-mono');
      if (!input) {{
        return {{ ok: false, reason: 'no-cron-input' }};
      }}
      const setter = Object.getOwnPropertyDescriptor(
        Object.getPrototypeOf(input), 'value',
      );
      const raw = {json.dumps(expr)};
      setter?.set.call(input, raw);
      input.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: raw }}));
      input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return new Promise(resolve => setTimeout(() => {{
        const text = document.body?.innerText || '';
        const hasPreview =
          /Weekdays at 09:30|Weekdays|工作日|09:30/.test(text);
        resolve({{ ok: true, hasPreview, sample: text.slice(0, 500) }});
      }}, 400));
    }})()"""


_BANNER_ABSENT_JS = """(() => {
  const banner = document.querySelector('[data-testid="cron-scheduler-health-banner"]');
  return { ready: banner === null };
})()"""

_BANNER_PRESENT_JS = """(() => {
  const banner = document.querySelector('[data-testid="cron-scheduler-health-banner"]');
  return { ready: banner !== null };
})()"""

_CLEAR_BANNER_DISMISS_JS = """(() => {
  try {
    sessionStorage.removeItem('myrm_cron_scheduler_banner_dismissed_status');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.timeout(300)
def test_cron_observability_ui_single_session() -> None:
    """Badge + CreateDialog preview + banner rules — one Chrome session."""
    api_base = get_e2e_api_url()
    health = http_json("GET", f"{api_base}/api/v1/cron/scheduler/health")
    assert isinstance(health, dict)
    assert health.get("status") in {"green", "yellow", "red"}

    prepare_e2e_ui_session(api_base)
    warm_ui_route("/settings/cron")
    warm_ui_route("/")

    with open_settings_subroute("/settings/cron", warm=False) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=10.0)
        dismiss_blocking_modals(client, page)

        settings_banner = wait_for_state(client, page, _BANNER_ABSENT_JS, timeout_sec=30.0)
        assert settings_banner.get("ready") is True, settings_banner

        badge = wait_for_state(client, page, _SCHEDULER_BADGE_JS, timeout_sec=90.0)
        assert badge.get("ready") is True, badge

        opened = wait_for_state(client, page, _OPEN_CREATE_DIALOG_JS, timeout_sec=60.0)
        assert opened.get("clicked") is True, opened

        dialog_ready = wait_for_state(client, page, _CREATE_DIALOG_READY_JS, timeout_sec=60.0)
        assert dialog_ready.get("ready") is True, dialog_ready

        switched = wait_for_state(client, page, _SWITCH_CUSTOM_TAB_JS, timeout_sec=30.0)
        assert switched.get("ready") is True, switched

        preview = client.evaluate(
            page,
            _set_cron_expr_js("30 9 * * 1-5"),
            timeout_sec=30.0,
        )
        assert isinstance(preview, dict)
        assert preview.get("ok") is True, preview
        assert preview.get("hasPreview") is True, preview

        ui_home = get_e2e_ui_url().rstrip("/") + "/"
        navigate_mcp_page(client, page, ui_home, timeout_ms=120_000)
        client.evaluate(page, _CLEAR_BANNER_DISMISS_JS, timeout_sec=10.0)
        dismiss_blocking_modals(client, page)

        if health.get("status") == "green":
            state = wait_for_state(client, page, _BANNER_ABSENT_JS, timeout_sec=45.0)
            assert state.get("ready") is True, state
        else:
            state = wait_for_state(client, page, _BANNER_PRESENT_JS, timeout_sec=45.0)
            assert state.get("ready") is True, state
