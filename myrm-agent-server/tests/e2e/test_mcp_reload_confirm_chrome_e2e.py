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

_MCP_PAGE_HAS_IMPORT_PROBE_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasHeading = /MCP 服务配置|MCP Service/i.test(text);
  const hasImport = text.includes('e2e-import-probe');
  return { ready: hasHeading && hasImport, sample: text.slice(0, 400) };
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
  const text = document.body?.innerText || '';
  const titleMatch = /重新加载 MCP 工具|Reload MCP tools|MCP.*neu laden|MCP.*다시 로드/i.test(text);
  const descMatch = /提示词缓存|prompt-cache|Prompt-Cache|프롬프트 캐시/i.test(text);
  const buttons = Array.from(document.querySelectorAll('button')).map((b) => (b.textContent || '').trim());
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
    buttons: buttons.slice(0, 20),
  };
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

_CLICK_IMPORT_JSON_BUTTON_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Import JSON|导入 JSON|JSON importieren|JSON 가져오기/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'import-button-not-found' };
  btn.click();
  return { ok: true };
})()"""

_CLICK_ADD_SERVICE_BUTTON_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Add Service|添加服务|Dienst hinzufügen|서비스 추가/i.test((b.textContent || '').trim())
  );
  if (!btn) return { ok: false, err: 'add-button-not-found' };
  btn.click();
  return { ok: true };
})()"""


def _set_import_textarea_js(value: str) -> str:
    escaped = json.dumps(value)
    return f"""(() => {{
  const heading = Array.from(document.querySelectorAll('h3')).find((h) =>
    /Import MCP Configuration|导入 MCP 配置|MCP-Konfiguration importieren|MCP 구성 가져오기/i.test(
      (h.textContent || '').trim()
    )
  );
  const modal = heading?.closest('div');
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
  const pattern = new RegExp({escaped_pattern}, 'i');
  const labels = Array.from(document.querySelectorAll('label'));
  const label = labels.find((node) => pattern.test((node.textContent || '').trim()));
  if (!label) return {{ ok: false, err: 'label-not-found' }};
  const container = label.closest('div');
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
  )?.closest('div');
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


def _confirm_reload_dialog(client, page, *, timeout_sec: float = 45.0) -> None:
    dialog = wait_for_state(client, page, _RELOAD_DIALOG_STATE_JS, timeout_sec=timeout_sec)
    assert dialog.get("ready") is True, json.dumps(dialog, ensure_ascii=False)
    confirmed = client.evaluate(page, _CLICK_DIALOG_CONFIRM_JS, timeout_sec=10.0)
    assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_mcp_reload_confirm_dialog_cancel_and_confirm_on_disable_toggle() -> None:
    """Disable toggle → reload dialog; cancel preserves config; confirm persists."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _seed_probe_mcp_server()
    assert _probe_enabled_in_api() is True

    warm_ui_route("/settings/mcp")
    with open_mcp_page(f"{ui_url}/settings/mcp", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        ready = wait_for_state(client, page, _MCP_PAGE_HAS_PROBE_JS, timeout_sec=90.0)
        assert ready.get("ready") is True, json.dumps(ready, ensure_ascii=False)

        toggled = client.evaluate(page, _TOGGLE_PROBE_SWITCH_JS, timeout_sec=15.0)
        assert isinstance(toggled, dict) and toggled.get("ok") is True, toggled

        dialog = wait_for_state(client, page, _RELOAD_DIALOG_STATE_JS, timeout_sec=30.0)
        assert dialog.get("ready") is True, json.dumps(dialog, ensure_ascii=False)

        cancelled = client.evaluate(page, _CLICK_DIALOG_CANCEL_JS, timeout_sec=10.0)
        assert isinstance(cancelled, dict) and cancelled.get("ok") is True, cancelled
        time.sleep(0.8)
        assert _probe_enabled_in_api() is True, "cancel must not persist disable"

        toggled_again = client.evaluate(page, _TOGGLE_PROBE_SWITCH_JS, timeout_sec=15.0)
        assert isinstance(toggled_again, dict) and toggled_again.get("ok") is True, toggled_again

        _confirm_reload_dialog(client, page)

        deadline = time.monotonic() + 20.0
        disabled = False
        while time.monotonic() < deadline:
            if not _probe_enabled_in_api():
                disabled = True
                break
            time.sleep(0.4)
        assert disabled is True, "confirm must persist disabled MCP server"


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_mcp_reload_confirm_dialog_on_delete() -> None:
    """Delete row → delete confirm → reload confirm → server removed from API."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _seed_probe_mcp_server()
    assert _server_exists_in_api(_PROBE_SERVER_NAME)

    warm_ui_route("/settings/mcp")
    with open_mcp_page(f"{ui_url}/settings/mcp", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        ready = wait_for_state(client, page, _MCP_PAGE_HAS_PROBE_JS, timeout_sec=90.0)
        assert ready.get("ready") is True, json.dumps(ready, ensure_ascii=False)

        clicked_delete = client.evaluate(page, _CLICK_PROBE_DELETE_JS, timeout_sec=15.0)
        assert isinstance(clicked_delete, dict) and clicked_delete.get("ok") is True, clicked_delete

        delete_dialog = wait_for_state(client, page, _DELETE_DIALOG_STATE_JS, timeout_sec=20.0)
        assert delete_dialog.get("ready") is True, json.dumps(delete_dialog, ensure_ascii=False)

        confirmed_delete = client.evaluate(page, _CLICK_DELETE_CONFIRM_JS, timeout_sec=10.0)
        assert isinstance(confirmed_delete, dict) and confirmed_delete.get("ok") is True, confirmed_delete

        _confirm_reload_dialog(client, page)
        _wait_for_server_absent(_PROBE_SERVER_NAME)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_mcp_reload_confirm_dialog_on_import_json() -> None:
    """Import JSON → reload confirm → imported server present in API."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _seed_empty_mcp_configs()
    assert not _server_exists_in_api(_IMPORT_SERVER_NAME)

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
        dismiss_blocking_modals(client, page)
        ready = wait_for_state(client, page, _MCP_PAGE_READY_JS, timeout_sec=90.0)
        assert ready.get("ready") is True, json.dumps(ready, ensure_ascii=False)

        opened = client.evaluate(page, _CLICK_IMPORT_JSON_BUTTON_JS, timeout_sec=15.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened

        filled = client.evaluate(
            page,
            _set_import_textarea_js(import_payload),
            timeout_sec=15.0,
        )
        assert isinstance(filled, dict) and filled.get("ok") is True, filled

        submitted = client.evaluate(page, _CLICK_IMPORT_SUBMIT_JS, timeout_sec=15.0)
        assert isinstance(submitted, dict) and submitted.get("ok") is True, submitted

        _confirm_reload_dialog(client, page, timeout_sec=90.0)
        _wait_for_server_present(_IMPORT_SERVER_NAME)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_mcp_reload_confirm_dialog_on_add_and_save() -> None:
    """Add Service form save → reload confirm → new server present in API."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _seed_empty_mcp_configs()
    assert not _server_exists_in_api(_ADD_SERVER_NAME)

    warm_ui_route("/settings/mcp")
    with open_mcp_page(f"{ui_url}/settings/mcp", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        ready = wait_for_state(client, page, _MCP_PAGE_READY_JS, timeout_sec=90.0)
        assert ready.get("ready") is True, json.dumps(ready, ensure_ascii=False)

        opened = client.evaluate(page, _CLICK_ADD_SERVICE_BUTTON_JS, timeout_sec=15.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened

        for label_pattern, value in (
            ("Service Name|服务名称|Dienstname|서비스 이름", _ADD_SERVER_NAME),
            ("Command|命令|Befehl|명령", sys.executable),
            ("Arguments|参数|Argumente|인수", "-c\npass"),
            ("Description|描述|Beschreibung|설명", "E2E add probe server"),
        ):
            filled = client.evaluate(
                page,
                _fill_input_by_label_js(label_pattern, value),
                timeout_sec=15.0,
            )
            assert isinstance(filled, dict) and filled.get("ok") is True, (label_pattern, filled)

        saved = client.evaluate(page, _CLICK_SAVE_CONFIG_JS, timeout_sec=15.0)
        assert isinstance(saved, dict) and saved.get("ok") is True, saved

        _confirm_reload_dialog(client, page, timeout_sec=90.0)
        _wait_for_server_present(_ADD_SERVER_NAME)

        ui_ready = wait_for_state(client, page, _MCP_PAGE_HAS_ADD_PROBE_JS, timeout_sec=60.0)
        assert ui_ready.get("ready") is True, json.dumps(ui_ready, ensure_ascii=False)
