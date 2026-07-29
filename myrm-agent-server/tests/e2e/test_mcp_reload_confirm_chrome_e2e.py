"""Chrome E2E: MCP settings reload-confirm dialog (M6 persistConfigs gate)."""

from __future__ import annotations

import json
import sys
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_PROBE_SERVER_NAME = "e2e-reload-probe"
_IMPORT_SERVER_NAME = "e2e-import-probe"
_ADD_SERVER_NAME = "e2e-add-probe"

_MCP_PAGE_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasHeading = /MCP 服务配置|MCP Service/i.test(text);
  return { ready: hasHeading, sample: text.slice(0, 400) };
})()"""

_MCP_PAGE_HAS_PROBE_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasHeading = /MCP 服务配置|MCP Service/i.test(text);
  const hasProbe = text.includes('e2e-reload-probe');
  return { ready: hasHeading && hasProbe, sample: text.slice(0, 400) };
})()"""

_MCP_PAGE_HAS_ADD_PROBE_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasHeading = /MCP 服务配置|MCP Service/i.test(text);
  const hasAdd = text.includes('e2e-add-probe');
  return { ready: hasHeading && hasAdd, sample: text.slice(0, 400) };
})()"""

_TOGGLE_PROBE_SWITCH_JS = """(() => {
  const nameNode = Array.from(document.querySelectorAll('p')).find((p) =>
    (p.textContent || '').trim() === 'e2e-reload-probe'
  );
  if (!nameNode) return { ok: false, err: 'probe-row-not-found' };
  const row = nameNode.closest('.group') || nameNode.parentElement?.parentElement?.parentElement;
  if (!row) return { ok: false, err: 'probe-row-container-not-found' };
  const switchBtn = row.querySelector('button[role="switch"]');
  if (!switchBtn) return { ok: false, err: 'switch-not-found' };
  switchBtn.click();
  return { ok: true };
})()"""

_CLICK_PROBE_DELETE_JS = """(() => {
  const nameNode = Array.from(document.querySelectorAll('p')).find((p) =>
    (p.textContent || '').trim() === 'e2e-reload-probe'
  );
  if (!nameNode) return { ok: false, err: 'probe-row-not-found' };
  const row = nameNode.closest('.group') || nameNode.parentElement?.parentElement?.parentElement;
  if (!row) return { ok: false, err: 'probe-row-container-not-found' };
  const trashIcon = row.querySelector('.text-red-500');
  const trashBtn = trashIcon?.closest('button');
  if (!trashBtn) return { ok: false, err: 'delete-not-found' };
  trashBtn.click();
  return { ok: true };
})()"""

_RELOAD_DIALOG_STATE_JS = """(() => {
  const alert = Array.from(document.querySelectorAll('[role="alertdialog"]')).find((node) => {
    const text = node.textContent || '';
    return /重新加载 MCP 工具|Reload MCP tools|MCP.*neu laden|MCP.*다시 로드/i.test(text);
  });
  if (!alert) {
    return {
      ready: false,
      titleMatch: false,
      descMatch: false,
      hasCancel: false,
      hasConfirm: false,
      buttons: [],
    };
  }
  const text = alert.textContent || '';
  const titleMatch = /重新加载 MCP 工具|Reload MCP tools|MCP.*neu laden|MCP.*다시 로드/i.test(text);
  const descMatch = /提示词缓存|prompt-cache|Prompt-Cache|프롬프트 캐시/i.test(text);
  const buttons = Array.from(alert.querySelectorAll('button')).map((b) =>
    (b.textContent || '').trim()
  );
  const hasCancel = buttons.some((b) => /^(取消|Cancel|Abbrechen|취소)$/i.test(b));
  const hasConfirm = buttons.some((b) =>
    /^(保存并应用|Save and apply|Speichern und anwenden|저장 및 적용)$/i.test(b)
  );
  return {
    ready: titleMatch && descMatch && hasCancel && hasConfirm,
    titleMatch,
    descMatch,
    hasCancel,
    hasConfirm,
    buttons,
  };
})()"""

_RELOAD_DIALOG_CLOSED_JS = """(() => {
  const alert = Array.from(document.querySelectorAll('[role="alertdialog"]')).find((node) => {
    const text = node.textContent || '';
    return /重新加载 MCP 工具|Reload MCP tools|MCP.*neu laden|MCP.*다시 로드/i.test(text);
  });
  return { ready: !alert };
})()"""

_DELETE_DIALOG_STATE_JS = """(() => {
  const text = document.body?.innerText || '';
  const titleMatch = /Confirm Delete|确认删除|Löschen bestätigen|삭제 확인/i.test(text);
  const buttons = Array.from(document.querySelectorAll('button')).map((b) => (b.textContent || '').trim());
  const hasCancel = buttons.some((b) => /^(取消|Cancel|Abbrechen|취소)$/i.test(b));
  const hasConfirm = buttons.some((b) => /^(Confirm Delete|确认删除|Löschen bestätigen|삭제 확인)$/i.test(b));
  return { ready: titleMatch && hasCancel && hasConfirm, titleMatch, hasCancel, hasConfirm };
})()"""

_CLICK_DIALOG_CANCEL_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /^(取消|Cancel|Abbrechen|취소)$/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'cancel-not-found' };
  btn.click();
  return { ok: true };
})()"""

_CLICK_DIALOG_CONFIRM_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /^(保存并应用|Save and apply|Speichern und anwenden|저장 및 적용)$/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'confirm-not-found' };
  btn.click();
  return { ok: true };
})()"""

_CLICK_DELETE_CONFIRM_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /^(Confirm Delete|确认删除|Löschen bestätigen|삭제 확인)$/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'delete-confirm-not-found' };
  btn.click();
  return { ok: true };
})()"""

_MCP_IMPORT_MODAL_READY_JS = """(() => {
  const heading = Array.from(document.querySelectorAll('h3')).find((h) =>
    /Import MCP Configuration|导入 MCP 配置|MCP-Konfiguration importieren|MCP 구성 가져오기/i.test(
      (h.textContent || '').trim()
    )
  );
  const modal = heading?.closest('.fixed.inset-0');
  const textarea = modal?.querySelector('textarea');
  return { ready: !!textarea, err: textarea ? null : 'import-textarea-not-found' };
})()"""

_CLICK_IMPORT_JSON_BUTTON_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Import JSON|导入 JSON|JSON importieren|JSON 가져오기/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'import-button-not-found' };
  btn.click();
  return { ok: true };
})()"""

_MCP_ADD_EDITOR_READY_JS = """(() => {
  const modal = document.querySelector('.fixed.inset-0');
  const heading = Array.from(modal?.querySelectorAll('h3') || []).find((h) =>
    /Add Service|添加服务|新增服務|追加サービス|Dienst hinzufügen|서비스 추가/i.test(
      (h.textContent || '').trim()
    )
  );
  const nameField = modal?.querySelector('input');
  return { ready: !!heading && !!nameField };
})()"""

_CLICK_ADD_SERVICE_BUTTON_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Add Service|添加服务|新增服務|追加サービス|Dienst hinzufügen|서비스 추가/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'add-button-not-found' };
  btn.click();
  return { ok: true };
})()"""

_SELECT_STDIO_CONNECTION_JS = """(() => {
  const modal = document.querySelector('.fixed.inset-0');
  if (!modal) return { ok: false, err: 'add-modal-not-found' };
  const findTypeTrigger = () => {
    const typeLabel = Array.from(modal.querySelectorAll('label, p.text-sm')).find((node) =>
      /Connection Type|连接类型|連線類型|接続タイプ|Verbindungstyp|연결 유형/i.test(
        (node.textContent || '').replace(/\\s+/g, ' ').trim()
      )
    );
    return typeLabel?.closest('.flex.flex-col')?.querySelector('button[type="button"]') || null;
  };
  const trigger = findTypeTrigger();
  if (!trigger) return { ok: false, err: 'connection-type-trigger-not-found' };
  const findStdio = () =>
    Array.from(document.querySelectorAll('button[type="button"]')).find((b) => {
      if (b === trigger) return false;
      return /\\bSTDIO\\b/i.test((b.textContent || '').replace(/\\s+/g, ' ').trim());
    }) || null;
  trigger.click();
  let stdioOption = null;
  for (let i = 0; i < 30; i++) {
    stdioOption = findStdio();
    if (stdioOption) break;
    const start = Date.now();
    while (Date.now() - start < 50) {}
  }
  if (!stdioOption) return { ok: false, err: 'stdio-option-not-found' };
  stdioOption.click();
  return { ok: true };
})()"""

_MCP_STDIO_FIELDS_READY_JS = """(() => {
  const modal = document.querySelector('.fixed.inset-0');
  const commandLabel = Array.from(modal?.querySelectorAll('label, p.text-sm') || []).find((node) =>
    /Command|命令|コマンド|Befehl|명령/i.test((node.textContent || '').replace(/\\s+/g, ' ').trim())
  );
  return { ready: !!commandLabel };
})()"""


def _set_import_textarea_js(value: str) -> str:
    escaped = json.dumps(value)
    return f"""(() => {{
  const heading = Array.from(document.querySelectorAll('h3')).find((h) =>
    /Import MCP Configuration|导入 MCP 配置|MCP-Konfiguration importieren|MCP 구성 가져오기/i.test(
      (h.textContent || '').trim()
    )
  );
  const modal = heading?.closest('.fixed.inset-0');
  const el = modal?.querySelector('textarea');
  if (!el) return {{ ok: false, err: 'import-textarea-not-found' }};
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return {{ ok: false, err: 'setter-not-found' }};
  setter.call(el, {escaped});
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return {{ ok: true }};
}})()"""


def _fill_input_by_label_js(label_pattern: str, value: str) -> str:
    escaped_value = json.dumps(value)
    escaped_pattern = json.dumps(label_pattern)
    return f"""(() => {{
  const modal = document.querySelector('.fixed.inset-0');
  if (!modal) return {{ ok: false, err: 'add-modal-not-found' }};
  const pattern = new RegExp({escaped_pattern}, 'i');
  const candidates = Array.from(modal.querySelectorAll('label, p.text-sm'));
  const label = candidates.find((node) => {{
    const text = (node.textContent || '').replace(/\\s+/g, ' ').trim();
    return pattern.test(text);
  }});
  if (!label) return {{ ok: false, err: 'label-not-found' }};
  const container = label.closest('.flex.flex-col') || label.parentElement;
  const el = container?.querySelector('input, textarea');
  if (!el) return {{ ok: false, err: 'input-not-found' }};
  const proto = el instanceof HTMLTextAreaElement
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (!setter) return {{ ok: false, err: 'setter-not-found' }};
  setter.call(el, {escaped_value});
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return {{ ok: true }};
}})()"""


_CLICK_IMPORT_SUBMIT_JS = """(() => {
  const modal = Array.from(document.querySelectorAll('h3')).find((h) =>
    /Import MCP Configuration|导入 MCP 配置|MCP-Konfiguration importieren|MCP 구성 가져오기/i.test(
      (h.textContent || '').trim()
    )
  )?.closest('.fixed.inset-0');
  const scope = modal || document;
  const btn = Array.from(scope.querySelectorAll('button')).find((b) =>
    /^(Import|导入|Importieren|가져오기)$/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'import-submit-not-found' };
  btn.click();
  return { ok: true };
})()"""

_CLICK_SAVE_CONFIG_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Save Configuration|保存配置|Konfiguration speichern|구성 저장/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'save-config-not-found' };
  btn.click();
  return { ok: true };
})()"""

_MCP_MODAL_VALIDATION_ERROR_JS = """(() => {
  const modal = document.querySelector('.fixed.inset-0');
  if (!modal) return { ready: true, hasError: false };
  const errBox = modal.querySelector('.text-red-600, .text-red-400');
  if (!errBox) return { ready: true, hasError: false };
  return {
    ready: false,
    hasError: true,
    error: (errBox.textContent || '').trim().slice(0, 500),
  };
})()"""

_ADD_MODAL_OPEN_JS = """(() => {
  const modal = document.querySelector('.fixed.inset-0');
  const heading = Array.from(modal?.querySelectorAll('h3') || []).find((h) =>
    /Add Service|添加服务|新增服務|追加サービス|Dienst hinzufügen|서비스 추가/i.test(
      (h.textContent || '').trim()
    )
  );
  return { ready: !!heading };
})()"""

_MCP_SAVE_VALIDATION_IDLE_JS = """(() => {
  const saveBtn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Save Configuration|保存配置|Konfiguration speichern|구성 저장/i.test((b.textContent || '').trim())
  );
  if (!saveBtn) return { ready: true, phase: 'no-save-btn' };
  const text = (saveBtn.textContent || '').trim();
  const validating = saveBtn.disabled || /Validating|验证|驗證|검증|Validierung/i.test(text);
  return { ready: !validating, validating, text };
})()"""

_CLICK_SCAN_ACK_CONFIRM_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Acknowledge and continue|了解风险并继续|瞭解風險並繼續|リスク.*続行|risques.*continuer/i.test(
      (b.textContent || '').trim()
    )
  );
  if (!btn) return { ok: false, err: 'scan-ack-not-found' };
  btn.click();
  return { ok: true };
})()"""

_CLICK_DESCRIPTION_CUSTOM_JS = """(() => {
  const heading = Array.from(document.querySelectorAll('h3')).find((h) =>
    /Choose Description|选择描述|選擇描述|説明を選択|Beschreibung wählen|설명 선택/i.test(
      (h.textContent || '').trim()
    )
  );
  if (!heading) return { ok: false, err: 'description-dialog-not-found' };
  const root = heading.closest('.fixed.inset-0') || document.body;
  const customLabel = Array.from(root.querySelectorAll('span')).find((s) =>
    /Custom Description|自定义描述|自訂描述|カスタム|Benutzerdefiniert|사용자/i.test(
      (s.textContent || '').trim()
    )
  );
  const btn = customLabel?.closest('button');
  if (!btn) return { ok: false, err: 'description-custom-not-found' };
  btn.click();
  return { ok: true };
})()"""

_LOCALHOST_PAGE_JS = """(() => {
  const host = location.hostname;
  return {
    ready: host === '127.0.0.1' || host === 'localhost',
    href: location.href,
  };
})()"""


def _fetch_mcp_servers_record() -> dict[str, object]:
    payload = http_json("GET", f"{get_e2e_api_url()}/api/v1/config/mcpServers")
    assert isinstance(payload, dict)
    return payload


def _list_mcp_server_names() -> list[str]:
    record = _fetch_mcp_servers_record()
    value = record.get("value")
    if not isinstance(value, dict):
        return []
    configs = value.get("mcpConfigs")
    if not isinstance(configs, list):
        return []
    names: list[str] = []
    for item in configs:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


def _probe_enabled_in_api() -> bool:
    record = _fetch_mcp_servers_record()
    value = record.get("value")
    if not isinstance(value, dict):
        return False
    configs = value.get("mcpConfigs")
    if not isinstance(configs, list):
        return False
    for item in configs:
        if isinstance(item, dict) and item.get("name") == _PROBE_SERVER_NAME:
            return item.get("enabled") is True
    return False


def _server_exists_in_api(name: str) -> bool:
    return name in _list_mcp_server_names()


def _put_mcp_configs(configs: list[dict[str, object]]) -> None:
    record = _fetch_mcp_servers_record()
    version = str(record.get("version") or "0")
    http_json(
        "PUT",
        f"{get_e2e_api_url()}/api/v1/config/mcpServers",
        {
            "deviceId": "web",
            "expectedVersion": version,
            "value": {"mcpConfigs": configs},
        },
    )


def _seed_probe_mcp_server(*, enabled: bool = True) -> None:
    probe = {
        "name": _PROBE_SERVER_NAME,
        "type": "stdio",
        "command": sys.executable,
        "args": ["-c", "pass"],
        "description": "E2E MCP reload confirm probe",
        "enabled": enabled,
        "headers": {},
        "extra_params": {},
    }
    _put_mcp_configs([probe])
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if _server_exists_in_api(_PROBE_SERVER_NAME):
            if not enabled or _probe_enabled_in_api():
                return
        time.sleep(0.4)
    raise AssertionError("failed to seed MCP probe server")


def _seed_empty_mcp_configs() -> None:
    _put_mcp_configs([])
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if _list_mcp_server_names() == []:
            return
        time.sleep(0.4)
    raise AssertionError("failed to seed empty MCP configs")


def _wait_for_server_absent(name: str, timeout_sec: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not _server_exists_in_api(name):
            return
        time.sleep(0.4)
    raise AssertionError(f"server {name!r} still present in API")


def _wait_for_server_present(name: str, timeout_sec: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _server_exists_in_api(name):
            return
        time.sleep(0.4)
    raise AssertionError(f"server {name!r} not present in API")


def _wait_for_probe_disabled(timeout_sec: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not _probe_enabled_in_api():
            return
        time.sleep(0.4)
    raise AssertionError("confirm must persist disabled MCP server")


def _confirm_reload_dialog(client, page, *, timeout_sec: float = 45.0) -> None:
    dialog = wait_for_state(
        client, page, _RELOAD_DIALOG_STATE_JS, timeout_sec=timeout_sec
    )
    assert dialog.get("ready") is True, json.dumps(dialog, ensure_ascii=False)
    confirmed = client.evaluate(page, _CLICK_DIALOG_CONFIRM_JS, timeout_sec=10.0)
    assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed
    wait_for_state(client, page, _RELOAD_DIALOG_CLOSED_JS, timeout_sec=30.0)


def _confirm_reload_dialog_after_save(
    client, page, *, timeout_sec: float = 120.0
) -> None:
    """Wait for async MCP save validation, intermediate ack dialogs, then reload confirm."""
    wait_for_state(client, page, _MCP_SAVE_VALIDATION_IDLE_JS, timeout_sec=90.0)
    err = client.evaluate(page, _MCP_MODAL_VALIDATION_ERROR_JS, timeout_sec=10.0)
    if isinstance(err, dict) and err.get("hasError") is True:
        raise AssertionError(f"MCP add/save validation failed: {err.get('error')!r}")
    target_url = f"{get_e2e_ui_url().rstrip('/')}/settings/mcp"
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    save_retries = 0
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            host = client.evaluate(
                page, _LOCALHOST_PAGE_JS, timeout_sec=min(10.0, remaining)
            )
        except (RuntimeError, TimeoutError):
            try:
                client.recover_mux_transport()
            except RuntimeError:
                pass
            reload_mcp_page(client, page, target_url=target_url)
            dismiss_blocking_modals(client, page)
            time.sleep(1.0)
            continue
        if not (isinstance(host, dict) and host.get("ready") is True):
            reload_mcp_page(client, page, target_url=target_url)
            dismiss_blocking_modals(client, page)
            time.sleep(1.0)
            continue
        handled_intermediate = False
        for intermediate_js in (
            _CLICK_SCAN_ACK_CONFIRM_JS,
            _CLICK_DESCRIPTION_CUSTOM_JS,
        ):
            result = client.evaluate(
                page, intermediate_js, timeout_sec=min(8.0, remaining)
            )
            if isinstance(result, dict) and result.get("ok") is True:
                handled_intermediate = True
                time.sleep(0.6)
                break
        if handled_intermediate:
            continue
        raw = client.evaluate(
            page, _RELOAD_DIALOG_STATE_JS, timeout_sec=min(10.0, remaining)
        )
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True:
            _confirm_reload_dialog(client, page, timeout_sec=min(45.0, remaining))
            return
        modal_open = client.evaluate(
            page, _ADD_MODAL_OPEN_JS, timeout_sec=min(8.0, remaining)
        )
        if (
            save_retries < 2
            and isinstance(modal_open, dict)
            and modal_open.get("ready") is True
        ):
            save_retries += 1
            retried = client.evaluate(page, _CLICK_SAVE_CONFIG_JS, timeout_sec=10.0)
            assert isinstance(retried, dict) and retried.get("ok") is True, retried
            wait_for_state(
                client, page, _MCP_SAVE_VALIDATION_IDLE_JS, timeout_sec=min(60.0, remaining)
            )
            continue
        time.sleep(0.4)
    raise AssertionError(f"reload confirm dialog after save did not appear: {last}")


_APP_LAYOUT_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="app-layout"]'),
}))()"""


def _reload_mcp_page(client, page) -> None:
    target_url = f"{get_e2e_ui_url().rstrip('/')}/settings/mcp"
    last: dict[str, object] = {}
    for attempt in range(3):
        reload_mcp_page(client, page, target_url=target_url)
        try:
            wait_for_state(client, page, _APP_LAYOUT_READY_JS, timeout_sec=120.0)
            dismiss_blocking_modals(client, page)
            return
        except AssertionError as exc:
            if attempt >= 2:
                raise
            last = {"attempt": attempt + 1, "error": str(exc)}
            time.sleep(2.0 * (attempt + 1))
    raise AssertionError(f"MCP page reload did not recover: {last}")


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_mcp_reload_confirm_dialog_all_paths_single_session() -> None:
    """Single SHPOIB session: toggle cancel/confirm, delete, import, add/save."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    import_payload = json.dumps(
        {
            "mcpServers": {
                _IMPORT_SERVER_NAME: {
                    "command": sys.executable,
                    "args": ["-c", "pass"],
                    "description": "E2E import probe server",
                }
            }
        }
    )

    warm_ui_route("/settings/mcp")
    with open_mcp_page(f"{ui_url}/settings/mcp", timeout_ms=120_000) as (client, page):
        # --- Path 1: disable toggle cancel + confirm ---
        _seed_probe_mcp_server()
        assert _probe_enabled_in_api() is True
        _reload_mcp_page(client, page)
        dismiss_blocking_modals(client, page)
        ready = wait_for_state(client, page, _MCP_PAGE_HAS_PROBE_JS, timeout_sec=90.0)
        assert ready.get("ready") is True, json.dumps(ready, ensure_ascii=False)

        toggled = client.evaluate(page, _TOGGLE_PROBE_SWITCH_JS, timeout_sec=15.0)
        assert isinstance(toggled, dict) and toggled.get("ok") is True, toggled
        dialog = wait_for_state(client, page, _RELOAD_DIALOG_STATE_JS, timeout_sec=30.0)
        assert dialog.get("ready") is True, json.dumps(dialog, ensure_ascii=False)
        cancelled = client.evaluate(page, _CLICK_DIALOG_CANCEL_JS, timeout_sec=10.0)
        assert isinstance(cancelled, dict) and cancelled.get("ok") is True, cancelled
        wait_for_state(client, page, _RELOAD_DIALOG_CLOSED_JS, timeout_sec=15.0)
        assert _probe_enabled_in_api() is True, "cancel must not persist disable"

        toggled_again = client.evaluate(page, _TOGGLE_PROBE_SWITCH_JS, timeout_sec=15.0)
        assert (
            isinstance(toggled_again, dict) and toggled_again.get("ok") is True
        ), toggled_again
        _confirm_reload_dialog(client, page)
        _wait_for_probe_disabled(timeout_sec=45.0)

        # --- Path 2: delete ---
        _seed_probe_mcp_server()
        _reload_mcp_page(client, page)
        ready_delete = wait_for_state(
            client, page, _MCP_PAGE_HAS_PROBE_JS, timeout_sec=90.0
        )
        assert ready_delete.get("ready") is True, json.dumps(
            ready_delete, ensure_ascii=False
        )

        clicked_delete = client.evaluate(page, _CLICK_PROBE_DELETE_JS, timeout_sec=15.0)
        assert (
            isinstance(clicked_delete, dict) and clicked_delete.get("ok") is True
        ), clicked_delete
        delete_dialog = wait_for_state(
            client, page, _DELETE_DIALOG_STATE_JS, timeout_sec=20.0
        )
        assert delete_dialog.get("ready") is True, json.dumps(
            delete_dialog, ensure_ascii=False
        )
        confirmed_delete = client.evaluate(
            page, _CLICK_DELETE_CONFIRM_JS, timeout_sec=10.0
        )
        assert (
            isinstance(confirmed_delete, dict) and confirmed_delete.get("ok") is True
        ), confirmed_delete
        _confirm_reload_dialog(client, page)
        _wait_for_server_absent(_PROBE_SERVER_NAME)

        # --- Path 3: import JSON ---
        _seed_empty_mcp_configs()
        _reload_mcp_page(client, page)
        ready_import = wait_for_state(
            client, page, _MCP_PAGE_READY_JS, timeout_sec=90.0
        )
        assert ready_import.get("ready") is True, json.dumps(
            ready_import, ensure_ascii=False
        )

        opened = client.evaluate(page, _CLICK_IMPORT_JSON_BUTTON_JS, timeout_sec=15.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened
        import_modal = wait_for_state(
            client, page, _MCP_IMPORT_MODAL_READY_JS, timeout_sec=30.0
        )
        assert import_modal.get("ready") is True, json.dumps(
            import_modal, ensure_ascii=False
        )
        filled = client.evaluate(
            page, _set_import_textarea_js(import_payload), timeout_sec=15.0
        )
        assert isinstance(filled, dict) and filled.get("ok") is True, filled
        submitted = client.evaluate(page, _CLICK_IMPORT_SUBMIT_JS, timeout_sec=15.0)
        assert isinstance(submitted, dict) and submitted.get("ok") is True, submitted
        _confirm_reload_dialog(client, page, timeout_sec=90.0)
        _wait_for_server_present(_IMPORT_SERVER_NAME)

        # --- Path 4: add/save form ---
        _seed_empty_mcp_configs()
        _reload_mcp_page(client, page)
        ready_add = wait_for_state(client, page, _MCP_PAGE_READY_JS, timeout_sec=90.0)
        assert ready_add.get("ready") is True, json.dumps(ready_add, ensure_ascii=False)

        opened_add = client.evaluate(
            page, _CLICK_ADD_SERVICE_BUTTON_JS, timeout_sec=15.0
        )
        assert isinstance(opened_add, dict) and opened_add.get("ok") is True, opened_add
        add_editor = wait_for_state(
            client, page, _MCP_ADD_EDITOR_READY_JS, timeout_sec=30.0
        )
        assert add_editor.get("ready") is True, json.dumps(
            add_editor, ensure_ascii=False
        )
        name_filled = client.evaluate(
            page,
            _fill_input_by_label_js(
                "Service Name|服务名称|服務名稱|サービス名前|Dienstname|서비스 이름",
                _ADD_SERVER_NAME,
            ),
            timeout_sec=15.0,
        )
        assert isinstance(name_filled, dict) and name_filled.get("ok") is True, name_filled
        selected_stdio: dict[str, object] = {"ok": False}
        for attempt in range(3):
            selected_stdio = client.evaluate(
                page, _SELECT_STDIO_CONNECTION_JS, timeout_sec=15.0
            )
            if isinstance(selected_stdio, dict) and selected_stdio.get("ok") is True:
                break
            time.sleep(1.0 * (attempt + 1))
        assert isinstance(selected_stdio, dict) and selected_stdio.get("ok") is True, (
            selected_stdio
        )
        stdio_ready = wait_for_state(
            client, page, _MCP_STDIO_FIELDS_READY_JS, timeout_sec=15.0
        )
        assert stdio_ready.get("ready") is True, json.dumps(
            stdio_ready, ensure_ascii=False
        )
        for label_pattern, value in (
            ("Command|命令|コマンド|Befehl|명령", sys.executable),
            ("Arguments|参数|參數|Argumente|인수", "-c\npass"),
            ("Description|描述|服務描述|サービス説明|Beschreibung|설명", "E2E add probe server"),
        ):
            filled_field = client.evaluate(
                page,
                _fill_input_by_label_js(label_pattern, value),
                timeout_sec=15.0,
            )
            assert isinstance(filled_field, dict) and filled_field.get("ok") is True, (
                label_pattern,
                filled_field,
            )
        saved = client.evaluate(page, _CLICK_SAVE_CONFIG_JS, timeout_sec=15.0)
        assert isinstance(saved, dict) and saved.get("ok") is True, saved
        _confirm_reload_dialog_after_save(client, page, timeout_sec=120.0)
        _wait_for_server_present(_ADD_SERVER_NAME)
        ui_ready = wait_for_state(
            client, page, _MCP_PAGE_HAS_ADD_PROBE_JS, timeout_sec=60.0
        )
        assert ui_ready.get("ready") is True, json.dumps(ui_ready, ensure_ascii=False)
