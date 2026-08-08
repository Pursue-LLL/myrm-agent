"""Chrome LIVE E2E: Workflow template Export bundle → delete → Import roundtrip."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    ensure_e2e_yolo_mode,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger

_TEMPLATE_ID = "e2e-export-import"
_DISPLAY_NAME = "E2E Export Import"
_MARKER = "E2E_EXPORT_IMPORT_MARKER"

_VALID_SCRIPT = f"""
import myrm_tools
myrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="{_MARKER}", readonly=True)
"""

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_LIBRARY_READY_JS = f"""(async () => {{
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const tab =
    tabs.find((node) =>
      /Workflow Templates|工作流模板|工作流範本|workflowTemplates/i.test(
        (node.textContent || '').trim(),
      ),
    ) ||
    document.querySelector('[role="tab"][value="workflowTemplates"]');
  if (
    tab &&
    tab.getAttribute('aria-selected') !== 'true' &&
    tab.getAttribute('data-state') !== 'active'
  ) {{
    tab.click();
  }}
  const library = document.querySelector('[data-testid="workflow-template-library"]');
  const hasLibraryRoot = !!library;
  const hasSettingsShell =
    !!document.querySelector('[data-testid="settings-layout"]') ||
    location.pathname.startsWith('/settings');
  const hasImport = !!library?.querySelector('input[type="file"][accept*="json"]');
  let hasTemplate = false;
  let apiStatus = 0;
  let apiCount = 0;
  try {{
    const response = await fetch('/api/v1/workflow-templates', {{
      credentials: 'include',
      cache: 'no-store',
    }});
    apiStatus = response.status;
    if (response.ok) {{
      const payload = await response.json();
      const items = Array.isArray(payload?.templates) ? payload.templates : [];
      apiCount = items.length;
      hasTemplate = items.some((item) => {{
        const id = item?.templateId ?? item?.template_id ?? '';
        const name = item?.displayName ?? item?.display_name ?? '';
        return id === '{_TEMPLATE_ID}' && name === '{_DISPLAY_NAME}';
      }});
    }}
  }} catch (err) {{
    apiStatus = -1;
  }}
  if (!hasTemplate && library) {{
    const refreshBtn = [...library.querySelectorAll('button')].find((btn) =>
      /Refresh|刷新|重新整理|refresh/i.test((btn.textContent || '').trim()),
    );
    if (refreshBtn && !refreshBtn.disabled) {{
      refreshBtn.click();
    }}
  }}
  const text = document.body?.innerText || '';
  const hasTemplateDom =
    text.includes('{_TEMPLATE_ID}') && text.includes('{_DISPLAY_NAME}');
  return {{
    ready:
      hasSettingsShell &&
      hasTemplate &&
      hasLibraryRoot &&
      hasImport &&
      text.length > 0,
    hasLibraryRoot,
    hasSettingsShell,
    hasImport,
    hasTemplate: hasTemplate || hasTemplateDom,
    apiStatus,
    apiCount,
    bodyLength: text.length,
    snippet: text.slice(0, 400),
  }};
}})()"""

_LIBRARY_ABSENT_JS = f"""(() => {{
  const text = document.body?.innerText || '';
  return {{
    ready: !text.includes('{_TEMPLATE_ID}'),
    hasTemplate: text.includes('{_TEMPLATE_ID}'),
  }};
}})()"""

_EXPORT_BUNDLE_JS = f"""(async () => {{
  const templateId = {_TEMPLATE_ID!r};
  const response = await fetch(
    `/api/v1/workflow-templates/${{encodeURIComponent(templateId)}}`,
    {{ credentials: 'include' }},
  );
  if (!response.ok) {{
    return {{ ok: false, status: response.status }};
  }}
  const detail = await response.json();
  const bundle = {{
    version: '1',
    template: {{
      templateId: detail.template?.templateId ?? detail.template?.template_id,
      displayName: detail.template?.displayName ?? detail.template?.display_name,
      scriptCode: detail.scriptCode ?? detail.script_code,
      trustLatch: detail.template?.trustLatch ?? detail.template?.trust_latch ?? false,
    }},
  }};
  const scriptCode = String(bundle.template.scriptCode || '');
  return {{
    ok: scriptCode.includes({_MARKER!r}),
    bundleJson: JSON.stringify(bundle, null, 2),
  }};
}})()"""

_CLICK_EXPORT_JS = f"""(() => {{
  const rows = [...document.querySelectorAll('.rounded-xl.border')];
  const row = rows.find((node) => (node.textContent || '').includes('{_TEMPLATE_ID}'));
  if (!row) {{
    return {{ ok: false, err: 'template-row-missing' }};
  }}
  const exportBtn = [...row.querySelectorAll('button')].find((btn) =>
    /Export|导出|匯出|エクスポート/i.test((btn.textContent || '').trim()),
  );
  if (!exportBtn || exportBtn.disabled) {{
    return {{ ok: false, err: 'export-button-missing-or-disabled' }};
  }}
  exportBtn.click();
  return {{ ok: true }};
}})()"""

_IMPORT_BUNDLE_JS = """async (bundleJson) => {
  const input = document.querySelector('input[type="file"][accept*="json"]');
  if (!input) {
    return { ok: false, err: 'file-input-missing' };
  }
  const file = new File([bundleJson], 'e2e-export-import.myrm-workflow.json', {
    type: 'application/json',
  });
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true };
}"""

_CLICK_REFRESH_JS = """(() => {
  const buttons = [...document.querySelectorAll('button')];
  const refreshBtn = buttons.find((btn) =>
    /Refresh|刷新|重新整理|更新/i.test((btn.textContent || '').trim()),
  );
  if (!refreshBtn || refreshBtn.disabled) {
    return { ok: false, err: 'refresh-button-missing-or-disabled' };
  }
  refreshBtn.click();
  return { ok: true };
})()"""


def _seed_template(api_base: str) -> None:
    http_json(
        "PUT",
        f"{api_base}/api/v1/workflow-templates/{_TEMPLATE_ID}",
        {
            "displayName": _DISPLAY_NAME,
            "scriptCode": _VALID_SCRIPT,
            "trustLatch": True,
        },
    )


def _verify_template_listed(api_base: str, *, expect_absent: bool = False) -> None:
    listed = http_json("GET", f"{api_base}/api/v1/workflow-templates")
    assert isinstance(listed, dict), listed
    templates = listed.get("templates")
    assert isinstance(templates, list), listed
    match = next(
        (item for item in templates if item.get("templateId") == _TEMPLATE_ID),
        None,
    )
    if expect_absent:
        assert match is None, listed
        return
    assert isinstance(match, dict), listed
    assert match.get("displayName") == _DISPLAY_NAME, match
    assert match.get("trustLatch") is True, match


def _delete_template(api_base: str) -> None:
    http_json(
        "DELETE",
        f"{api_base}/api/v1/workflow-templates/{_TEMPLATE_ID}",
        expected_statuses=frozenset({200, 404}),
    )


_TRANSPORT_RETRY_MARKERS = (
    "CDP request timeout",
    "Operation timeout: navigate",
    "Browser Orchestrator error",
    "Browser Orchestrator response timeout",
    "daemon not running",
    "Timeout (>510.0s)",
    "socket",
)


def _is_transport_retryable(exc: BaseException) -> bool:
    message = str(exc)
    return any(marker in message for marker in _TRANSPORT_RETRY_MARKERS)


def _force_mux_heal_before_retry() -> None:
    from tests.support.e2e_runtime_guard import _heal_stale_e2e_lease

    _heal_stale_e2e_lease()
    time.sleep(2.0)


def _run_export_import_roundtrip(*, api_base: str) -> None:
    subroute = "/settings/skills?sub=workflowTemplates"
    ui_base = get_e2e_ui_url().rstrip("/")
    page_url = f"{ui_base}{subroute}"
    with open_settings_subroute(
        subroute,
        layout_timeout_sec=120.0,
    ) as (client, page):
        ready: dict[str, object] = {}
        for attempt in range(3):
            ready = wait_for_state(
                client,
                page,
                _LIBRARY_READY_JS,
                timeout_sec=120.0,
                page_url=page_url,
                blank_heal_mode="direct",
            )
            if ready.get("ready") is True and ready.get("hasLibraryRoot") is True:
                break
            if attempt < 2:
                reload_mcp_page(
                    client, page, target_url=page_url, timeout_ms=120_000
                )
        assert ready.get("ready") is True, json.dumps(
            ready, indent=2, ensure_ascii=False
        )
        if ready.get("hasLibraryRoot") is not True:
            reload_mcp_page(
                client, page, target_url=page_url, timeout_ms=120_000
            )
            dom_ready = wait_for_state(
                client,
                page,
                _LIBRARY_READY_JS,
                timeout_sec=90.0,
                page_url=page_url,
                blank_heal_mode="direct",
            )
            assert dom_ready.get("hasLibraryRoot") is True, json.dumps(
                dom_ready, indent=2, ensure_ascii=False
            )

        export_click = client.evaluate(page, _CLICK_EXPORT_JS, timeout_sec=15.0)
        assert isinstance(export_click, dict)
        assert export_click.get("ok") is True, f"Export click failed: {export_click}"

        exported = client.evaluate(page, _EXPORT_BUNDLE_JS, timeout_sec=30.0)
        assert isinstance(exported, dict), exported
        assert exported.get("ok") is True, f"Export bundle failed: {exported}"
        bundle_json = exported.get("bundleJson")
        assert isinstance(bundle_json, str) and _MARKER in bundle_json, exported

        _delete_template(api_base)

        refreshed = client.evaluate(page, _CLICK_REFRESH_JS, timeout_sec=15.0)
        assert isinstance(refreshed, dict)
        assert refreshed.get("ok") is True, f"Refresh click failed: {refreshed}"

        absent = wait_for_state(
            client,
            page,
            _LIBRARY_ABSENT_JS,
            timeout_sec=60.0,
            page_url=page_url,
            blank_heal_mode="direct",
        )
        assert absent.get("ready") is True, json.dumps(
            absent, indent=2, ensure_ascii=False
        )

        imported = client.evaluate(
            page,
            f"({ _IMPORT_BUNDLE_JS })({json.dumps(bundle_json)})",
            timeout_sec=60.0,
        )
        assert isinstance(imported, dict), imported
        assert imported.get("ok") is True, f"Import dispatch failed: {imported}"

        restored = wait_for_state(
            client,
            page,
            _LIBRARY_READY_JS,
            timeout_sec=90.0,
            page_url=page_url,
            blank_heal_mode="direct",
        )
        assert restored.get("ready") is True, json.dumps(
            restored, indent=2, ensure_ascii=False
        )


def _run_with_transport_retry(*, api_base: str) -> None:
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            _run_export_import_roundtrip(api_base=api_base)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= 3 or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_workflow_template_export_import_roundtrip_chrome_e2e(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Export v1 JSON from library context, remove template, import via file picker, verify script."""
    _ = e2e_resource_ledger
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail(
            "Provider not ready — run ./myrm ready --chrome then ./myrm test -m chrome_e2e "
            "myrm-agent/myrm-agent-server/tests/e2e/test_workflow_template_export_import_chrome_e2e.py",
        )

    ensure_e2e_yolo_mode()
    api_base = get_e2e_api_url()

    _delete_template(api_base)
    _seed_template(api_base)
    _verify_template_listed(api_base)

    prepare_e2e_ui_session(api_base)

    try:
        _run_with_transport_retry(api_base=api_base)

        _verify_template_listed(api_base)
    finally:
        _delete_template(api_base)
