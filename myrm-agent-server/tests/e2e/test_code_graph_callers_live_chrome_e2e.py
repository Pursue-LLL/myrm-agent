"""Chrome LIVE E2E: a real-model turn in a trusted project folder answers "who calls select" through ``code_graph_tool``.

The folder holds a function ``select``, a class ``Select`` and three calls in ``app.py``: ``select(...)`` on line 5,
``db.select(...)`` on line 6 and ``db.Select(...)`` on line 7. The user switches the preset skill ``repo-call-graph`` on,
links the folder to a project, trusts it and asks for the callers of ``select``. Everything runs through the real UI, the real
server and a real provider.

- The stored assistant message records the ``code_graph_tool`` call with the action ``callers`` and the query ``select``.
- The rendered chat shows ``app.py:5``, the call site of the lower-case name, and never ``app.py:7``, the ``db.Select`` call.

``tests/api/agent/test_code_graph_tool_e2e.py`` asserts the rows the tool returns; this test covers the browser side.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import quote

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    e2e_runtime_bootstrap_apply_js,
    ensure_e2e_yolo_mode,
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, http_json, open_mcp_page  # noqa: E402
from tests.support.e2e_lite_model_pin import pin_lite_model_for_e2e  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once  # noqa: E402

SKILL_ID = "repo-call-graph"
TOOL_NAME = "code_graph_tool"
PROMPT = (
    "Use the code_graph_tool with the action callers and the query select (all lowercase) to find who calls the "
    "function select in this project. Answer with one file:line per call site and nothing else."
)
CORE_PY = "def select(items):\n    return items[0]\n\n\nclass Select:\n    pass\n"
APP_PY = (
    "from core import Select, select\n\n\ndef run(items, db):\n    first = select(items)\n    db.select(items)\n"
    "    db.Select(items)\n    return first, Select()\n"
)
CALLERS_CALL = "action: callers | query: select"
TURN_WITHIN_SECONDS = 240.0
STORED_WITHIN_SECONDS = 60.0
LOG_TAIL_CHARS = 6000

_AGENT_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const debug = bridge?.debugProviderState?.() ?? {};
  return { ready: !!bridge?.handleSubmit && !!debug.selection };
})()"""

_TURN_STATE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const shown = document.body?.innerText || '';
  return {
    isStreaming: Boolean(snap.isStreaming),
    userCount: snap.userCount ?? 0,
    sample: String(snap.lastAssistantSample || '').slice(0, 300),
    shows_call_site: shown.includes('app.py:5'),
    shows_case_mismatch: shown.includes('app.py:7'),
  };
})()"""


@asynccontextmanager
async def _ready_chat(url: str) -> AsyncIterator[McpChatSession]:
    """The UI at ``url`` with its E2E bridge ready and the LITE model pinned."""
    with open_mcp_page(url, timeout_ms=120_000) as (client, page):
        chat = McpChatSession(client, page)
        await chat.bootstrap(url, timeout_sec=180.0)
        bootstrap_js = e2e_runtime_bootstrap_apply_js()
        if bootstrap_js:
            applied = await chat.evaluate(bootstrap_js, intent=EvaluateIntent.AGENT_SUBMIT)
            assert isinstance(applied, dict) and applied.get("ok") is True, applied
        else:
            await chat.ensure_e2e_api_base_binding()
        await chat.dismiss_modals()

        deadline = time.monotonic() + 90.0
        ready: object = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            ready = await chat.evaluate(_AGENT_READY_JS, intent=EvaluateIntent.BRIDGE_POLL)
            if isinstance(ready, dict) and ready.get("ready") is True:
                break
            await asyncio.sleep(1.0)
        assert isinstance(ready, dict) and ready.get("ready") is True, ready

        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        await pin_lite_model_for_e2e(chat)
        yield chat


@contextmanager
def _skill_enabled(api_base: str) -> Iterator[None]:
    """What the user does in Settings: switch the preset skill on, approve the permission it asks for, switch it on again."""
    skill_api = f"{api_base}/api/v1/skills/{SKILL_ID}"
    enabled = http_json("POST", f"{skill_api}/enable")
    assert isinstance(enabled, dict)
    granted: list[str] = []
    if enabled.get("pending_approval"):
        granted = [str(permission) for permission in enabled["required_permissions"]]
        http_json("POST", f"{skill_api}/permissions/grant", {"permissions": granted})
        enabled = http_json("POST", f"{skill_api}/enable")
        assert isinstance(enabled, dict)
    assert enabled.get("enabled") is True, enabled
    try:
        yield
    finally:
        http_json("POST", f"{skill_api}/disable")
        if granted:
            http_json("POST", f"{skill_api}/permissions/revoke", {"permissions": granted})


@contextmanager
def _trusted_project_chat(api_base: str, folder: Path, ledger: E2EResourceLedger) -> Iterator[str]:
    """What a user does before asking: link ``folder`` to a project, put a chat in it, preview the folder and trust what was shown."""
    created = http_json("POST", f"{api_base}/api/v1/projects/", {"name": f"Code graph LIVE {uuid.uuid4().hex[:8]}"})
    assert isinstance(created, dict)
    project_id = str(created["data"]["project"]["id"])
    ledger.register("project", project_id)
    trust_api = f"{api_base}/api/v1/security/workspace-trust"
    try:
        http_json("PUT", f"{api_base}/api/v1/projects/{project_id}", {"workspace_path": str(folder)})
        chat_id = f"code-graph-live-{uuid.uuid4().hex[:10]}"
        http_json("POST", f"{api_base}/api/v1/chats/", {"chat_id": chat_id})
        ledger.register("chat", chat_id)
        http_json("PATCH", f"{api_base}/api/v1/projects/chats/{chat_id}/project", {"projectId": project_id})
        shown = http_json("POST", f"{trust_api}/manifest", {"path": str(folder)})
        assert isinstance(shown, dict)
        http_json(
            "POST",
            f"{trust_api}/decide",
            {"path": str(folder), "level": "TRUSTED", "manifest_hash": shown["data"]["manifest_hash"]},
        )
        yield chat_id
    finally:
        try:
            http_json("DELETE", f"{trust_api}?path={quote(str(folder), safe='')}&remove=true")
        except RuntimeError:
            pass


def _dicts(value: object) -> list[dict[str, object]]:
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _stored_turns(chat_id: str, api_base: str) -> list[dict[str, object]]:
    return _dicts(fetch_chat_messages(chat_id, api_url=api_base))


def _is_tool_step(step: dict[str, object]) -> bool:
    return step.get("tool_name") == TOOL_NAME or str(step.get("step_key", "")).startswith(TOOL_NAME)


def _stored_tool_steps(chat_id: str, api_base: str) -> list[dict[str, object]]:
    """The ``code_graph_tool`` steps recorded on the completed assistant turns of a chat."""
    steps: list[dict[str, object]] = []
    for message in _stored_turns(chat_id, api_base):
        metadata = message.get("metadata")
        if message.get("role") != "assistant" or not isinstance(metadata, dict) or metadata.get("completionStatus") != "complete":
            continue
        steps.extend(step for step in _dicts(metadata.get("progressSteps")) if _is_tool_step(step))
    return steps


def _wait_for_stored_tool_steps(chat_id: str, api_base: str) -> list[dict[str, object]]:
    """The page shows a finished stream slightly before the server has stored the assistant turn, so the store is polled."""
    deadline = time.monotonic() + STORED_WITHIN_SECONDS
    while True:
        steps = _stored_tool_steps(chat_id, api_base)
        if steps:
            return steps
        if time.monotonic() >= deadline:
            stored = [
                (m.get("role"), metadata.get("completionStatus") if isinstance(metadata := m.get("metadata"), dict) else None)
                for m in _stored_turns(chat_id, api_base)
            ]
            raise AssertionError(
                f"no completed assistant turn recorded a {TOOL_NAME} step within {STORED_WITHIN_SECONDS}s; stored turns: {stored}"
            )
        time.sleep(2.0)


def _backend_log_tail() -> str:
    """The end of the private backend's own log, which is reaped with the runtime and says why a turn produced nothing."""
    log_file = Path(os.environ.get("MYRM_BACKEND_LOG_FILE", ""))
    return log_file.read_text(encoding="utf-8", errors="replace")[-LOG_TAIL_CHARS:] if log_file.is_file() else "no backend log"


async def _turn_state(chat: McpChatSession) -> dict[str, object]:
    raw = await chat.evaluate(_TURN_STATE_JS, intent=EvaluateIntent.BRIDGE_POLL)
    return raw if isinstance(raw, dict) else {"value": raw}


async def _wait_until_the_turn_shows_the_call_site(chat: McpChatSession) -> None:
    deadline = time.monotonic() + TURN_WITHIN_SECONDS
    state: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_once()
        state = await _turn_state(chat)
        if (
            state.get("isStreaming") is False
            and int(str(state.get("userCount") or 0)) >= 1
            and state.get("shows_call_site") is True
        ):
            return
        await asyncio.sleep(1.5)
    raise AssertionError(f"the rendered chat never showed app.py:5: {state}\nbackend log tail:\n{_backend_log_tail()}")


def _recorded_calls(steps: list[dict[str, object]]) -> list[str]:
    """The ``action | query`` texts of the tool steps."""
    return [str(item.get("text", "")) for step in steps for item in _dicts(step.get("items"))]


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="LIVE",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_callers_of_a_lower_case_name_are_rendered_after_a_real_model_turn(
    e2e_resource_ledger: E2EResourceLedger, tmp_path: Path
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for the live E2E — run via ./myrm-dev test -m chrome_e2e after ./myrm-dev ready --chrome"
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url().rstrip("/")
    ensure_e2e_yolo_mode(api_url=api_base)
    folder = tmp_path / "linked"
    folder.mkdir()
    (folder / "core.py").write_text(CORE_PY, encoding="utf-8")
    (folder / "app.py").write_text(APP_PY, encoding="utf-8")

    with _skill_enabled(api_base), _trusted_project_chat(api_base, folder, e2e_resource_ledger) as chat_id:
        async with _ready_chat(f"{ui_base}/") as chat:
            await chat.send_message(PROMPT, PROMPT, chat_id_hint=chat_id)
            await chat.wait_stream_started(PROMPT, timeout_sec=120.0, chat_id_hint=chat_id)
            await chat.navigate_to_chat(chat_id, ui_base, timeout_sec=90.0)

            await _wait_until_the_turn_shows_the_call_site(chat)
            calls = _recorded_calls(_wait_for_stored_tool_steps(chat_id, api_base))
            assert CALLERS_CALL in calls, f"the stored tool steps do not record {CALLERS_CALL!r}: {calls}"

            final = await _turn_state(chat)
            assert final.get("shows_case_mismatch") is False, (
                f"the rendered chat lists app.py:7, the db.Select call, as a caller of select: {final}"
            )
