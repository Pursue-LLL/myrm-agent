"""Chrome LIVE E2E: a real-model turn in a workspace that also holds hostile files shows the rule file's codeword in the page.

The chat workspace holds an ``AGENTS.md`` with a codeword nobody else knows, a FIFO where a skill's ``SKILL.md`` should be, and
sparse multi-megabyte ``mcp.json`` and ``.myrm/config.toml``. The turn runs through the real UI, the real server and a real
provider; the final answer has to carry the codeword in the rendered chat and in the stored assistant message.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

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
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="FIFOs and sparse files are POSIX")

CODEWORD = "KRAKATOA-7731"
PROMPT = "What is the project codeword? Answer with the codeword only."
SPARSE_BYTES = 64 * 1024 * 1024
TURN_WITHIN_SECONDS = 240.0

_PIN_LITE_MODEL_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinLiteModelForE2e) return { ok: false, err: 'no-pinLiteModelForE2e' };
  return bridge.pinLiteModelForE2e().then((pinned) => ({ ok: true, pinned }));
})()"""

_AGENT_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const debug = bridge?.debugProviderState?.() ?? {};
  return { ready: !!bridge?.handleSubmit && !!debug.selection };
})()"""

_ENSURE_CHAT_SESSION_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.ensureChatSession) return { ok: false, err: 'no ensureChatSession' };
  return bridge.ensureChatSession().then(() => ({ ok: true }));
})()"""

_TURN_STATE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const shown = document.body?.innerText || '';
  return {
    isStreaming: Boolean(snap.isStreaming),
    userCount: snap.userCount ?? 0,
    sample: String(snap.lastAssistantSample || '').slice(0, 300),
    rendered: shown.toUpperCase().includes('__CODEWORD__'),
  };
})()"""


def _create_agent(api_url: str) -> str:
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        {
            "name": f"Hostile Folder LIVE {uuid.uuid4().hex[:8]}",
            "description": "Chrome LIVE E2E: workspace rules next to hostile files",
            "system_prompt": "You are a test agent. Follow the project rules of the workspace and answer briefly.",
            "skill_ids": [],
            "mcp_ids": [],
            "enabled_builtin_tools": ["code_execute"],
            "security_overrides": {"yoloModeEnabled": True, "yolo_mode_enabled_at": time.time()},
        },
    )
    assert isinstance(created, dict)
    data = created.get("data")
    agent_id = data.get("id") if isinstance(data, dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    return agent_id


def _plant_workspace(workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text(
        f"Project Convention: the project codeword is {CODEWORD}. When the user asks for the project codeword, "
        "answer with exactly that word.\n",
        encoding="utf-8",
    )
    honest = workspace / "skills" / "honest"
    honest.mkdir(parents=True)
    (honest / "SKILL.md").write_text(
        "---\nname: honest\ndescription: A skill the folder really ships.\n---\n\nBody.\n", encoding="utf-8"
    )
    hostile = workspace / "skills" / "hostile"
    hostile.mkdir()
    os.mkfifo(hostile / "SKILL.md")
    (workspace / ".myrm").mkdir(exist_ok=True)
    for sparse in (workspace / "mcp.json", workspace / ".myrm" / "config.toml"):
        with sparse.open("wb") as handle:
            handle.truncate(SPARSE_BYTES)


def _release_blocked_readers(workspace: Path) -> None:
    """Unblock a backend thread still waiting to open the FIFO, so a server without the fix recovers once the test is over."""
    try:
        os.close(os.open(workspace / "skills" / "hostile" / "SKILL.md", os.O_WRONLY | os.O_NONBLOCK))
    except OSError:  # ENXIO or the file is gone: nobody is waiting on it
        pass


def _stored_answer(chat_id: str, api_url: str) -> str:
    answers = [
        str(message.get("content") or "")
        for message in fetch_chat_messages(chat_id, api_url=api_url)
        if message.get("role") == "assistant"
    ]
    return answers[-1] if answers else ""


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_the_codeword_of_the_rule_file_is_rendered_after_a_real_model_turn_in_a_hostile_workspace(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for the live E2E — run via ./myrm-dev test -m chrome_e2e after ./myrm-dev ready --chrome"
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url().rstrip("/")
    ensure_e2e_yolo_mode(api_url=api_base)
    agent_id = _create_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)
    workspace: Path | None = None

    try:
        with open_mcp_page(f"{ui_base}/?agentId={agent_id}", timeout_ms=120_000) as (client, page):
            chat = McpChatSession(client, page)
            await chat.bootstrap(f"{ui_base}/?agentId={agent_id}", timeout_sec=180.0)
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
            pinned = await chat.evaluate(_PIN_LITE_MODEL_JS, intent=EvaluateIntent.AGENT_SUBMIT)
            assert isinstance(pinned, dict) and pinned.get("ok") is True, pinned
            await chat.click_new_chat()
            await chat.ensure_chat_surface(ui_base)
            ensured = await chat.evaluate(_ENSURE_CHAT_SESSION_JS, intent=EvaluateIntent.ROUTE_ATTACH)
            assert isinstance(ensured, dict) and ensured.get("ok") is True, ensured

            chat_id = str((await chat.bridge_chat_id()) or "").strip()
            assert chat_id, "Expected a client chat id before seeding the workspace"
            seeded = http_json("POST", f"{api_base}/api/v1/chats/test/seed-file-edit-batch-workspace?chat_id={chat_id}")
            assert isinstance(seeded, dict)
            workspace = Path(str(seeded["file_path"])).parent
            _plant_workspace(workspace)

            sent = await chat.send_message(PROMPT, PROMPT)
            hint = str(sent.get("started", {}).get("chatId") or sent.get("submit", {}).get("chatId") or chat_id).strip()
            started = await chat.wait_stream_started(PROMPT, timeout_sec=120.0, chat_id_hint=hint or None)
            resolved = hint or str(started.get("chatId") or "").strip()
            assert resolved, f"Expected a chat id after the stream started: {started}"
            e2e_resource_ledger.register("chat", resolved)
            await chat.navigate_to_chat(resolved, ui_base, timeout_sec=90.0)

            deadline = time.monotonic() + TURN_WITHIN_SECONDS
            state: dict[str, object] = {}
            while time.monotonic() < deadline:
                heartbeat_once()
                raw = await chat.evaluate(_TURN_STATE_JS.replace("__CODEWORD__", CODEWORD), intent=EvaluateIntent.BRIDGE_POLL)
                state = raw if isinstance(raw, dict) else {"value": raw}
                if (
                    state.get("isStreaming") is False
                    and int(str(state.get("userCount") or 0)) >= 1
                    and state.get("rendered") is True
                ):
                    break
                await asyncio.sleep(1.5)

            assert state.get("rendered") is True, f"the rendered chat never showed the codeword: {state}"
            assert CODEWORD in _stored_answer(resolved, api_base).upper()
    finally:
        if workspace is not None:
            _release_blocked_readers(workspace)
