"""Chrome E2E: linking a project folder that holds hostile files opens the FolderGate with the honest counts.

The folder holds one honest skill, one honest rule file, a FIFO where a second skill's ``SKILL.md`` should be, and sparse
multi-megabyte ``mcp.json`` and ``.myrm/config.toml``. Linking it from the project menu asks the server for a preview first;
the dialog must come back with the counts of what a reader can really use instead of waiting on the FIFO.

Flow: project chip context menu -> Set Workspace -> Choose folder -> type the path -> Use this folder -> FolderGate.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="FIFOs and sparse files are POSIX")

SPARSE_BYTES = 64 * 1024 * 1024
GATE_WITHIN_SECONDS = 30.0

_SKILL_MD = "---\nname: honest\ndescription: A skill the folder really ships.\n---\n\nBody.\n"

_CHIP_CONTEXT_MENU_JS = """(() => {
  const name = __NAME__;
  const chip = Array.from(document.querySelectorAll('button')).find((el) => (el.textContent || '').trim() === name);
  if (!chip) return { ready: false, reason: 'chip-missing' };
  const box = chip.getBoundingClientRect();
  chip.dispatchEvent(new MouseEvent('contextmenu', {
    bubbles: true, cancelable: true, clientX: box.x + 4, clientY: box.y + 4,
  }));
  return { ready: true };
})()"""

_CLICK_BY_TEXT_JS = """(() => {
  const pattern = new RegExp(__PATTERN__, 'i');
  const target = Array.from(document.querySelectorAll('button')).find(
    (el) => !el.disabled && pattern.test((el.textContent || '').trim()),
  );
  if (!target) return { ready: false, reason: 'button-missing' };
  target.click();
  return { ready: true };
})()"""

# The picker loads the home folder when it opens and then writes that path into the input; typing earlier would be overwritten.
_PICKER_LOADED_JS = """(() => {
  const input = Array.from(document.querySelectorAll('input')).find((el) => /Enter path|输入路径/.test(el.placeholder || ''));
  return { ready: !!input && input.value.length > 0 };
})()"""

_TYPE_PATH_JS = """(() => {
  const input = Array.from(document.querySelectorAll('input')).find((el) => /Enter path|输入路径/.test(el.placeholder || ''));
  if (!input) return { ready: false, reason: 'path-input-missing' };
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(input, __PATH__);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  return { ready: true };
})()"""

# React commits the typed value in a microtask, so Enter has to arrive in a separate evaluation to read it.
_PRESS_ENTER_JS = """(() => {
  const input = Array.from(document.querySelectorAll('input')).find((el) => /Enter path|输入路径/.test(el.placeholder || ''));
  if (!input) return { ready: false, reason: 'path-input-missing' };
  input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  return { ready: true };
})()"""

_PATH_SHOWN_JS = """(() => {
  const text = document.body.innerText || '';
  return { ready: text.includes(__PATH__), page: text.slice(0, 300) };
})()"""

_USE_THIS_FOLDER_JS = """(() => {
  const target = Array.from(document.querySelectorAll('button[title]')).find(
    (el) => !el.disabled && /Use this folder|使用此文件夹/.test(el.getAttribute('title') || ''),
  );
  if (!target) return { ready: false, reason: 'use-this-folder-disabled-or-missing' };
  target.click();
  return { ready: true };
})()"""

_GATE_STATE_JS = """(() => {
  const dialog = document.querySelector('[role="alertdialog"]');
  const text = dialog ? dialog.innerText || '' : '';
  const count = (label) => {
    const hit = new RegExp('(?:' + label + ')\\\\s*(\\\\d+)', 'i').exec(text);
    return hit ? Number(hit[1]) : null;
  };
  const skills = count('Local skills|本地技能');
  const shownPath = dialog ? (dialog.querySelector('p.font-mono') || {}).innerText || null : null;
  return {
    ready: /Trust this folder\\?|是否信任此文件夹/.test(text) && skills !== null,
    skills,
    rules: count('Workspace rules|工作区规则'),
    mcp: count('Local MCP servers|本地 MCP 服务'),
    hasConfig: /Contains a \\.myrm project config|包含 \\.myrm 项目配置/.test(text),
    shownPath,
  };
})()"""


def _plant_hostile_folder(root: Path) -> None:
    (root / ".myrm").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Rules\nUse tabs.\n", encoding="utf-8")
    honest = root / "skills" / "honest"
    honest.mkdir(parents=True)
    (honest / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    hostile = root / "skills" / "hostile"
    hostile.mkdir()
    os.mkfifo(hostile / "SKILL.md")
    for sparse in (root / "mcp.json", root / ".myrm" / "config.toml"):
        with sparse.open("wb") as handle:
            handle.truncate(SPARSE_BYTES)


def _release_blocked_readers(fifo: Path) -> None:
    """Unblock a backend thread still waiting to open the FIFO, so a server without the fix recovers once the test is over."""
    try:
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
    except OSError:  # ENXIO: nobody is waiting on the FIFO
        pass


def _create_project(api_url: str, name: str) -> str:
    created = http_json("POST", f"{api_url}/api/v1/projects/", {"name": name})
    assert isinstance(created, dict)
    data = created.get("data")
    project = data.get("project", data) if isinstance(data, dict) else created
    project_id = project.get("id") if isinstance(project, dict) else None
    assert isinstance(project_id, str) and project_id, created
    return project_id


def _delete_project(api_url: str, project_id: str) -> None:
    try:
        http_json("DELETE", f"{api_url}/api/v1/projects/{project_id}", expected_statuses=frozenset({200, 204}))
    except RuntimeError:
        pass


def _step(client: ChromeMcpClient, page: McpPage, expression: str, *, timeout_sec: float = 30.0) -> dict[str, object]:
    state = wait_for_state(client, page, expression, timeout_sec=timeout_sec)
    assert state.get("ready") is True, state
    return state


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_folder_gate_discloses_the_honest_counts_of_a_folder_with_hostile_files(tmp_path: Path) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    folder = tmp_path / "hostile"
    _plant_hostile_folder(folder)
    name = f"Folder Gate {uuid.uuid4().hex[:8]}"
    project_id = _create_project(api_url, name)

    try:
        with open_mcp_page(f"{ui_url.rstrip('/')}/", request_timeout_sec=300.0) as (client, page):
            dismiss_blocking_modals(client, page)
            _step(client, page, _CHIP_CONTEXT_MENU_JS.replace("__NAME__", json.dumps(name)), timeout_sec=60.0)
            _step(client, page, _CLICK_BY_TEXT_JS.replace("__PATTERN__", json.dumps("^Set Workspace$|^设置工作目录$")))
            _step(client, page, _CLICK_BY_TEXT_JS.replace("__PATTERN__", json.dumps("^Choose folder$|^选择文件夹$")))
            _step(client, page, _PICKER_LOADED_JS)
            _step(client, page, _TYPE_PATH_JS.replace("__PATH__", json.dumps(str(folder.resolve()))))
            _step(client, page, _PRESS_ENTER_JS)
            _step(client, page, _PATH_SHOWN_JS.replace("__PATH__", json.dumps(str(folder.resolve()))))
            _step(client, page, _USE_THIS_FOLDER_JS)

            started = time.monotonic()
            gate = _step(client, page, _GATE_STATE_JS, timeout_sec=GATE_WITHIN_SECONDS)
            elapsed = time.monotonic() - started

            assert elapsed < GATE_WITHIN_SECONDS, json.dumps(gate)
            assert gate["shownPath"] == str(folder.resolve()), json.dumps(gate)
            assert (gate["skills"], gate["rules"], gate["mcp"], gate["hasConfig"]) == (1, 1, 1, True), json.dumps(gate)
            _step(client, page, _CLICK_BY_TEXT_JS.replace("__PATTERN__", json.dumps("^Cancel$|^取消$")))
    finally:
        _release_blocked_readers(folder / "skills" / "hostile" / "SKILL.md")
        _delete_project(api_url, project_id)
