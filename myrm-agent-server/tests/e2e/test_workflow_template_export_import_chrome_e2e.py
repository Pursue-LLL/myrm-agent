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
    DISMISS_MODALS_JS,
    ensure_e2e_yolo_mode,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from chrome_mcp_client import ChromeMcpClient  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

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

_CLICK_WORKFLOW_TEMPLATES_TAB_JS = """(() => {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const tab = tabs.find((node) =>
    /Workflow Templates|工作流模板|工作流範本|ワークフローテンプレート/i.test(
      (node.textContent || '').trim(),
    ),
  );
  if (tab && tab.getAttribute('aria-selected') !== 'true') {
    tab.click();
  }
  return { ok: !!tab, selected: tab?.getAttribute('aria-selected') === 'true' };
})()"""

_LIBRARY_READY_JS = f"""(() => {{
  const text = document.body?.innerText || '';
  const hasSettingsShell = !!document.querySelector('[data-testid="settings-layout"]');
  const hasImport =
    /Import|导入|匯入|インポート/i.test(text);
  const hasTemplate = text.includes('{_TEMPLATE_ID}') && text.includes('{_DISPLAY_NAME}');
  return {{
    ready: hasSettingsShell && hasImport && hasTemplate,
    hasSettingsShell,
    hasImport,
    hasTemplate,
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


def _client_navigate(client: ChromeMcpClient, page: object, url: str) -> None:
    """In-page navigation — avoids CDP Page.navigate stalls under parallel Chrome load."""
    client.evaluate(
        page,
        f"(() => {{ window.location.href = {json.dumps(url)}; return location.href; }})()",
        timeout_sec=15.0,
    )


def _is_transport_retryable(exc: BaseException) -> bool:
    message = str(exc)
    return any(marker in message for marker in _TRANSPORT_RETRY_MARKERS)


def _force_mux_heal_before_retry() -> None:
    from tests.support.e2e_runtime_guard import _heal_stale_e2e_lease

    _heal_stale_e2e_lease()
    time.sleep(2.0)


def _run_export_import_roundtrip(
    *, library_url: str, api_base: str, use_cdp_navigate: bool
) -> None:
    open_url = library_url if use_cdp_navigate else "about:blank"
    with open_mcp_page(
        open_url,
        timeout_ms=90_000,
        request_timeout_sec=120.0,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        if not use_cdp_navigate:
            _client_navigate(client, page, library_url)
            time.sleep(3.0)

        dismiss_blocking_modals(client, page, recover_url=library_url)
        client.evaluate(page, DISMISS_MODALS_JS, timeout_sec=10.0)
        heartbeat_e2e_lease()

        tab_click = client.evaluate(
            page, _CLICK_WORKFLOW_TEMPLATES_TAB_JS, timeout_sec=15.0
        )
        assert isinstance(tab_click, dict)
        assert tab_click.get("ok") is True, f"Tab click failed: {tab_click}"

        ready = wait_for_state(
            client,
            page,
            _LIBRARY_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert ready.get("ready") is True, json.dumps(
            ready, indent=2, ensure_ascii=False
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
        )
        assert restored.get("ready") is True, json.dumps(
            restored, indent=2, ensure_ascii=False
        )


def _run_with_transport_retry(*, library_url: str, api_base: str) -> None:
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            _run_export_import_roundtrip(
                library_url=library_url,
                api_base=api_base,
                use_cdp_navigate=(attempt >= 2),
            )
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
    ui_url = get_e2e_ui_url()
    library_url = f"{ui_url.rstrip('/')}/settings/skills"

    _delete_template(api_base)
    _seed_template(api_base)

    prepare_e2e_ui_session(api_base)

    try:
        _run_with_transport_retry(library_url=library_url, api_base=api_base)

        detail = http_json(
            "GET", f"{api_base}/api/v1/workflow-templates/{_TEMPLATE_ID}"
        )
        assert isinstance(detail, dict), detail
        script_code = str(detail.get("scriptCode", ""))
        assert _MARKER in script_code, detail
        assert detail.get("template", {}).get("trustLatch") is True, detail
    finally:
        _delete_template(api_base)
