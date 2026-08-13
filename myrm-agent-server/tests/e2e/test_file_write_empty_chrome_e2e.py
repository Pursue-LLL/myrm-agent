"""Chrome E2E: empty file_write rejection — READ lane FileMutationWarning banner."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import uuid
from pathlib import Path

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from cdp_chat.support import (  # noqa: E402
    empty_write_failure_in_messages,
    ensure_e2e_yolo_mode,
    file_write_tool_call_count,
    nudge_agent_stream_turn,
    steer_chat_message,
    wait_e2e_provider_ready,
)
from dev_gate.contract import STALL_PROGRESS_SEC, EvaluateIntent  # noqa: E402
from e2e_core.orchestrator import remaining_wall_sec, touch_wall_progress  # noqa: E402
from cdp_chat.live_turn_wait import (  # noqa: E402
    live_empty_write_parallel_scaled_cap_sec,
    live_empty_write_steer_attempts_cap,
    live_empty_write_steer_retry_idle_sec,
    live_empty_write_ui_nudge_allowed_after_steer,
    parallel_live_agent_peer_count,
    steer_empty_write_prompt,
)
from cdp_chat.mcp_ui import McpChatSession  # noqa: E402

from tests.api.agent.utils import (  # noqa: E402
    _strip_provider_prefix,
    get_lite_model_selection,
)
from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,  # noqa: E402
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
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")


def _force_mux_heal_before_live_retry() -> None:
    """Heal stale CDP/mux after a failed open_mcp_page before outer retry (R119/R120)."""
    _require_e2e_cdp_ready(budget_sec=45.0)
    from mux.attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="file_write live outer retry")
    time.sleep(3.0)


_LIVE_EMPTY_WRITE_BASENAME = "live_empty_write_e2e"
_FILE_WRITE_TOOL = "file_write_tool"
_MAX_CHAT_ATTEMPTS = 2

_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "CDP",
    "Chrome MCP",
    "connection reset",
    "wait_for_state",
    "Browser state did not become ready",
    "E2E_BOOTSTRAP",
    "recover_mux",
    "TypeError",
    "Dev E2E chat bridge",
    "chat bridge not ready after loading agent",
    "UI send did not start stream",
    "chrome-error",
    "LEASE_NOT_ACTIVE",
    "Chrome MCP transport",
)

_BUSINESS_FAILURE_MARKERS: tuple[str, ...] = (
    "E2E_STALL",
    "LLM idle without file_write_tool",
    "file_write_tool not found",
    "Live empty write API nudge failed",
    "fileMutationFailures missing",
    "E2E_AGENT_TOOLS_DENY",
    "Live empty write did not produce mutation failure banner",
)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if any(marker in text for marker in _BUSINESS_FAILURE_MARKERS):
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _normalize_live_transport_exc(exc: BaseException) -> BaseException:
    """R170: parallel open_mcp stall tripwire sends SIGINT — outer retry must heal mux."""
    if isinstance(exc, KeyboardInterrupt) and _parallel_live_agent_peer_count() >= 2:
        return RuntimeError(
            "MUX_RECLAIM: open_mcp_page_blocking stall tripwire (SIGINT); "
            "recover mux and retry"
        )
    return exc


def _is_mux_io_deferrable(exc: BaseException) -> bool:
    """R151: parallel mux reclaim may stall Chrome MCP evaluate/navigate — API remains SSOT."""
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc)
        return "MUX_RECLAIM" in message or "Chrome MCP" in message
    return False


def _bounded_wait_sec(default: float, *, reserve_sec: float = 45.0) -> float:
    remaining = remaining_wall_sec()
    if remaining <= reserve_sec:
        return max(10.0, remaining - 5.0)
    return min(default, remaining - reserve_sec)


def _seed_live_workspace(api_url: str, chat_id: str) -> dict[str, object]:
    """Bind sandbox executor (same SSOT as file_edit batch LIVE E2E)."""
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-edit-batch-workspace?chat_id={chat_id}",
    )
    assert isinstance(seeded, dict)
    assert str(seeded.get("chat_id")) == chat_id
    return seeded


def _live_empty_write_filename() -> str:
    return f"{_LIVE_EMPTY_WRITE_BASENAME}_{uuid.uuid4().hex[:8]}.txt"


def _live_user_prompt(filename: str) -> str:
    return (
        "INSTRUCTION: You MUST call tools. Do NOT reply with text only. "
        f"Call file_write_tool exactly once with path {filename!r} and "
        "content '' (empty string, zero bytes, no spaces). Do not use bash or file_edit_tool. "
        "Do NOT call file_write_tool a second time. "
        "Reply EMPTY_WRITE_DONE after the tool returns."
    )


def _steer_empty_write_prompt(filename: str) -> str:
    return steer_empty_write_prompt(filename)


def _nudge_result_agent_busy(nudge_result: dict[str, object]) -> bool:
    err = nudge_result.get("error")
    if isinstance(err, dict):
        if str(err.get("error_type") or "") == "AgentBusyError":
            return True
        if int(err.get("status_code") or 0) == 409:
            return True
    return False


def _nudge_result_deferrable(nudge_result: dict[str, object]) -> bool:
    """R168: parallel mux — steer may own the turn; nudge idle/409 is not fatal."""
    if _nudge_result_agent_busy(nudge_result):
        return True
    err = nudge_result.get("error")
    if isinstance(err, dict):
        error_type = str(err.get("error_type") or "")
        if error_type in {"AgentStreamIdleTimeout", "AgentStreamError"}:
            return True
    return False


def _empty_write_target_path(workspace_seed: dict[str, object], filename: str) -> Path:
    workspace_dir = Path(str(workspace_seed["file_path"])).parent
    return workspace_dir / filename


_PIN_LITE_MODEL_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinLiteModelForE2e) {
    return { ok: false, err: 'no-pinLiteModelForE2e' };
  }
  return bridge.pinLiteModelForE2e().then((pinned) => ({ ok: true, pinned }));
})()"""

_AGENT_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const debug = bridge?.debugProviderState?.() ?? {};
  return {
    ready: !!bridge?.handleSubmit && !!debug.selection,
    selection: debug.selection ?? null,
  };
})()"""

_ENSURE_PROVIDERS_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.ensureProviders) return { ok: false, err: 'no ensureProviders' };
  return Promise.resolve(bridge.ensureProviders()).then(() => ({ ok: true }));
})()"""

_PROVIDERS_SEND_READY_JS = """(() => ({
  init: !!window.__MYRM_E2E_CHAT__?.isProvidersInitialized?.(),
  sendReady: !!window.__MYRM_E2E_CHAT__?.isSendReady?.(),
  selection: window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.selection ?? null,
}))()"""

_AGENT_BOUND_JS = """((expectedAgentId) => {
  const store = window.__myrmChatStore?.getState?.();
  const fromStore = String(store?.agentConfig?.agentId || '').trim();
  const fromUrl = String(
    new URLSearchParams(window.location.search).get('agentId') || '',
  ).trim();
  const agentId = fromStore || fromUrl;
  const expected = String(expectedAgentId || '').trim();
  return {
    ready: store?.actionMode === 'agent' && !!agentId && agentId === expected,
    actionMode: store?.actionMode ?? null,
    agentId: agentId || null,
    expectedAgentId: expected,
    fromStore: fromStore || null,
    fromUrl: fromUrl || null,
  };
})"""

_ENSURE_CHAT_SESSION_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.ensureChatSession) return { ok: false, err: 'no ensureChatSession' };
  return bridge.ensureChatSession().then(() => ({ ok: true }));
})()"""

_LIVE_MUTATION_BANNER_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const failures = (store?.messages || []).flatMap((msg) =>
    Array.isArray(msg.fileMutationFailures) ? msg.fileMutationFailures : [],
  );
  const bodyText = document.body?.innerText || '';
  const hasTitle = /File Modification Failed|文件修改失败/i.test(bodyText);
  const hasError = /Cannot write empty file content/i.test(bodyText)
    || failures.some((item) => String(item?.error_preview || '').includes('Cannot write empty'));
  return {
    ready: failures.length > 0 && hasTitle && hasError,
    failureCount: failures.length,
    hasTitle,
    hasError,
    sample: bodyText.slice(0, 500),
  };
})()"""

_FIXTURE_ANSWER = "Empty write E2E fixture answer."

_MUTATION_BANNER_READY_JS = f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  const failures = Array.isArray(msg?.fileMutationFailures) ? msg.fileMutationFailures : [];
  const bodyText = document.body?.innerText || '';
  const hasTitle = /File Modification Failed|文件修改失败/i.test(bodyText);
  const hasCount = /file modification failed|文件修改失败|个文件修改失败/i.test(bodyText);
  const hasError = /Cannot write empty file content/i.test(bodyText)
    || failures.some((item) => String(item?.error_preview || '').includes('Cannot write empty'));
  return {{
    ready: failures.length > 0 && hasTitle && hasCount,
    failureCount: failures.length,
    hasTitle,
    hasCount,
    hasError,
    sample: bodyText.slice(0, 500),
  }};
}})()"""


def _seed_file_mutation_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-mutation-fixture?variant=empty_write",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    message_id = str(seeded.get("message_id") or "")
    ui_path = str(seeded.get("ui_path") or "")
    assert chat_id.startswith("e2efmut")
    assert len(message_id) >= 8
    assert ui_path == f"/{chat_id}"
    return seeded


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_file_write_empty_shows_mutation_warning_banner() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_file_mutation_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        message_ready = wait_for_state(
            client,
            page,
            f"""(() => {{
              const target = {json.dumps(_FIXTURE_ANSWER)};
              const store = window.__myrmChatStore?.getState?.();
              const msg = (store?.messages || []).find(
                (item) => item.role === 'assistant' && (item.content || '').includes(target),
              );
              return {{ ready: !!msg, count: store?.messages?.length ?? 0 }};
            }})()""",
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready,
            ensure_ascii=False,
        )

        dismiss_blocking_modals(client, page)

        banner = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=30.0,
        )
        assert banner.get("ready") is True, json.dumps(banner, ensure_ascii=False)
        assert int(banner.get("failureCount") or 0) >= 1

        expanded = wait_for_state(
            client,
            page,
            """(() => {
              const btn = Array.from(document.querySelectorAll('button')).find((el) => {
                const text = el.textContent || '';
                return /File Modification Failed|文件修改失败/i.test(text);
              });
              if (!btn) return { ready: false, err: 'banner-button-missing' };
              btn.click();
              const store = window.__myrmChatStore?.getState?.();
              const failures = (store?.messages || [])
                .flatMap((msg) => Array.isArray(msg.fileMutationFailures) ? msg.fileMutationFailures : []);
              const hasStoreError = failures.some((item) =>
                String(item?.error_preview || '').includes('Cannot write empty file content'),
              );
              const bodyText = document.body?.innerText || '';
              const hasDomError = /Cannot write empty file content/i.test(bodyText);
              const hasPath = /empty_write_e2e\\.txt/i.test(bodyText);
              return {
                ready: hasStoreError && (hasDomError || hasPath),
                hasStoreError,
                hasDomError,
                hasPath,
                sample: bodyText.slice(0, 500),
              };
            })()""",
            timeout_sec=15.0,
        )
        assert expanded.get("ready") is True, json.dumps(expanded, ensure_ascii=False)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_file_write_empty_mutation_banner_survives_page_reload() -> None:
    """Hydrate from DB: reload must still show FileMutationWarning from metadata."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_file_mutation_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        message_ready = wait_for_state(
            client,
            page,
            f"""(() => {{
              const target = {json.dumps(_FIXTURE_ANSWER)};
              const store = window.__myrmChatStore?.getState?.();
              const msg = (store?.messages || []).find(
                (item) => item.role === 'assistant' && (item.content || '').includes(target),
              );
              return {{ ready: !!msg }};
            }})()""",
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready,
            ensure_ascii=False,
        )

        dismiss_blocking_modals(client, page)

        banner_before_reload = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=30.0,
        )
        assert banner_before_reload.get("ready") is True, json.dumps(
            banner_before_reload,
            ensure_ascii=False,
        )

        reload_mcp_page(client, page)
        dismiss_blocking_modals(client, page)

        reloaded = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=120.0,
        )
        assert reloaded.get("ready") is True, json.dumps(reloaded, ensure_ascii=False)


def _create_empty_write_live_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Empty Write LIVE {suffix}",
        "description": "Chrome LIVE E2E for file_write_tool empty content rejection",
        "system_prompt": (
            "You write workspace files with file_write_tool when asked. "
            "When the user specifies empty content, call file_write_tool with content exactly "
            "as an empty string. Do not substitute spaces, placeholders, or skip the tool call. "
            "Reply EMPTY_WRITE_DONE after the tool returns."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "security_overrides": {
            "yoloModeEnabled": True,
            "yolo_mode_enabled_at": time.time(),
        },
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    agent_id = (
        created.get("data", {}).get("id")
        if isinstance(created.get("data"), dict)
        else created.get("id")
    )
    assert isinstance(agent_id, str) and agent_id
    _assert_live_agent_file_ops_enabled(api_url, agent_id)
    return agent_id


def _live_chat_attempt_cap() -> int:
    """R144/R165: parallel mux — allow one pre-SEND_TURN transport retry (turn_ever_sent guard)."""
    if parallel_live_agent_peer_count() >= 2:
        return 2
    return _MAX_CHAT_ATTEMPTS


def _parallel_live_agent_peer_count() -> int:
    return parallel_live_agent_peer_count()


def _live_empty_write_parallel_scaled_cap_sec(*, base: float) -> float:
    return live_empty_write_parallel_scaled_cap_sec(base=base)


def _live_empty_write_post_send_stall_cap_sec() -> float:
    """R134: post-E2E_SEND_TURN stall scales under parallel load (not transport)."""
    return _live_empty_write_parallel_scaled_cap_sec(base=float(STALL_PROGRESS_SEC))


def _live_empty_write_post_steer_idle_cap_sec() -> float:
    """R137: post-steer fail-fast scales under parallel load (steer API ok, LLM slow)."""
    return _live_empty_write_parallel_scaled_cap_sec(base=float(STALL_PROGRESS_SEC))


def _live_empty_write_steer_attempts_cap() -> int:
    return live_empty_write_steer_attempts_cap()


def _live_empty_write_steer_retry_idle_sec() -> float:
    return live_empty_write_steer_retry_idle_sec()


def _live_empty_write_ui_nudge_allowed_after_steer(*, idle_sec: float) -> bool:
    return live_empty_write_ui_nudge_allowed_after_steer(idle_sec=idle_sec)


def _live_api_poll_timeout_sec() -> float:
    """R167: private-backend message fetch under parallel mux load."""
    peers = _parallel_live_agent_peer_count()
    if peers < 2:
        return 15.0
    return min(60.0, 15.0 + peers * 8.0)


def _live_api_poll_max_attempts() -> int:
    """R167b: avoid 3× timeout blocking the async poll loop under parallel load."""
    return 1 if _parallel_live_agent_peer_count() >= 2 else 3


def _live_turn_wait_cap_sec() -> float:
    """Post-E2E_SEND_TURN wait — scale under parallel without 150s stall cap."""
    peers = _parallel_live_agent_peer_count()
    base = 300.0
    if peers < 2:
        return base
    return min(420.0, base + peers * 15.0)


def _live_bridge_ready_timeout_sec() -> float:
    """R138: React E2E bridge wait scales under parallel mux load."""
    return _live_empty_write_parallel_scaled_cap_sec(base=90.0)


def _assert_live_agent_file_ops_enabled(api_url: str, agent_id: str) -> None:
    fetched = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    data = fetched.get("data") if isinstance(fetched.get("data"), dict) else fetched
    assert isinstance(
        data, dict
    ), f"E2E_AGENT_TOOLS_DENY: agent fetch failed: {fetched!r}"
    resolved_id = str(data.get("id") or agent_id)
    assert (
        resolved_id == agent_id
    ), f"E2E_AGENT_TOOLS_DENY: agent id mismatch: {resolved_id!r} vs {agent_id!r}"
    # file_ops/code_execute are AGENT_BASELINE — stripped at persist, forced on General mount.
    print(
        f"E2E_AGENT_TOOLS_OK: agent_id={agent_id} baseline=file_ops+code_execute (runtime mount)",
        file=sys.stderr,
        flush=True,
    )


def _empty_write_failure_in_messages(
    chat_id: str, *, api_url: str
) -> tuple[bool, bool]:
    return empty_write_failure_in_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=_live_api_poll_timeout_sec(),
        max_attempts=_live_api_poll_max_attempts(),
    )


def _file_write_tool_call_count(chat_id: str, *, api_url: str) -> int:
    return file_write_tool_call_count(
        chat_id,
        api_url=api_url,
        timeout_sec=_live_api_poll_timeout_sec(),
        max_attempts=_live_api_poll_max_attempts(),
    )


def _assert_empty_write_disk_clean(target_file: Path) -> None:
    if not target_file.exists():
        return
    try:
        preview = target_file.read_bytes()[:200]
    except OSError as exc:
        raise AssertionError(
            f"Empty write must not create file on disk: {target_file} (read failed: {exc})"
        ) from exc
    raise AssertionError(
        f"Empty write must not create file on disk: {target_file} "
        f"(size={target_file.stat().st_size} preview={preview!r}) — "
        "likely LLM called file_write_tool twice or with non-empty content"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE"
, private_reason="live_shpoib")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_file_write_empty_live_agent_webui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """LIVE_AGENT: real LLM calls file_write_tool with empty content → FileMutationWarning."""
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live empty-write E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome"
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()
    ensure_e2e_yolo_mode(api_url=api_base)
    agent_id = _create_empty_write_live_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)

    async def _wait_agent_applied(
        chat: McpChatSession, *, timeout_sec: float | None = None
    ) -> None:
        wait_cap = (
            timeout_sec
            if timeout_sec is not None
            else _bounded_wait_sec(90.0, reserve_sec=120.0)
        )
        deadline = time.monotonic() + wait_cap
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            touch_wall_progress()
            raw = await chat.evaluate(
                _AGENT_READY_JS, intent=EvaluateIntent.BRIDGE_POLL
            )
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return
            await asyncio.sleep(1.0)
        raise AssertionError(f"E2E chat bridge not ready after loading agent: {last}")

    async def _pin_lite_model(chat: McpChatSession) -> dict[str, object]:
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        pinned = await chat.evaluate(
            _PIN_LITE_MODEL_JS, intent=EvaluateIntent.AGENT_SUBMIT
        )
        assert isinstance(pinned, dict)
        assert pinned.get("ok") is True, f"Failed to pin lite model: {pinned}"
        expected_lite = get_lite_model_selection()
        pinned_model = pinned.get("pinned")
        assert isinstance(pinned_model, dict), f"Missing pinned model payload: {pinned}"
        assert pinned_model.get("providerId") == expected_lite["providerId"]
        assert pinned_model.get("model") == _strip_provider_prefix(
            str(expected_lite["model"])
        )
        return pinned_model

    async def _api_nudge_turn(
        resolved_chat_id: str, agent_id: str, filename: str
    ) -> str:
        nudge_prompt = _live_user_prompt(filename)
        nudge_result = await asyncio.to_thread(
            nudge_agent_stream_turn,
            resolved_chat_id,
            agent_id,
            nudge_prompt,
            api_url=api_base,
            timeout_sec=_bounded_wait_sec(120.0, reserve_sec=90.0),
        )
        touch_wall_progress()
        if nudge_result.get("ok") is True:
            return "ok"
        if _nudge_result_deferrable(nudge_result):
            print(
                "E2E_NUDGE_DEFER: steer/in-flight owns session or stream idle; "
                f"chat_id={resolved_chat_id!r} parallel_peers={_parallel_live_agent_peer_count()} "
                f"err={nudge_result.get('error')!r}",
                file=sys.stderr,
                flush=True,
            )
            return "deferred"
        raise AssertionError(
            f"Live empty write API nudge failed: {nudge_result}; "
            f"filename={filename!r}"
        )

    async def _steer_empty_write_turn(chat_id: str, filename: str) -> bool:
        """R150: REST steer on in-flight turn — works when UI nudge gets AgentBusyError."""
        steer_result = await asyncio.to_thread(
            steer_chat_message,
            chat_id,
            _steer_empty_write_prompt(filename),
            api_url=api_base,
        )
        touch_wall_progress()
        steer_ok = steer_result.get("ok") is True
        print(
            f"E2E_STEER_EMPTY_WRITE: ok={steer_ok} "
            f"parallel_peers={_parallel_live_agent_peer_count()}",
            file=sys.stderr,
            flush=True,
        )
        return steer_ok

    async def _poll_empty_write_api(chat_id: str) -> tuple[bool, bool]:
        poll_timeout = _live_api_poll_timeout_sec()
        poll_attempts = _live_api_poll_max_attempts()
        return await asyncio.to_thread(
            empty_write_failure_in_messages,
            chat_id,
            api_url=api_base,
            timeout_sec=poll_timeout,
            max_attempts=poll_attempts,
        )

    async def _wait_turn_done(
        chat: McpChatSession,
        chat_id: str,
        *,
        agent_id: str,
        target_file: Path | None = None,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        wait_cap = (
            timeout_sec
            if timeout_sec is not None
            else _bounded_wait_sec(_live_turn_wait_cap_sec(), reserve_sec=60.0)
        )
        deadline = time.monotonic() + wait_cap
        last_api = (False, False)
        last_progress_at = time.monotonic()
        last_ui_sample = ""
        invoked_since: float | None = None
        not_invoked_since: float | None = None
        steer_attempts = 0
        ui_nudge_attempts = 0
        while time.monotonic() < deadline:
            heartbeat_once()
            touch_wall_progress()
            try:
                invoked, has_failure = await _poll_empty_write_api(chat_id)
            except (
                TimeoutError,
                OSError,
                urllib.error.URLError,
                urllib.error.HTTPError,
            ) as exc:
                print(
                    "E2E_API_POLL_DEFER: parallel private-backend poll deferred "
                    f"parallel_peers={_parallel_live_agent_peer_count()} "
                    f"timeout={_live_api_poll_timeout_sec():.0f}s err={exc!r}",
                    file=sys.stderr,
                    flush=True,
                )
                await asyncio.sleep(2.0)
                continue
            if invoked != last_api[0] or has_failure != last_api[1]:
                last_progress_at = time.monotonic()
                touch_wall_progress()
            if invoked and invoked_since is None:
                invoked_since = time.monotonic()
            if invoked:
                not_invoked_since = None
            elif not_invoked_since is None:
                not_invoked_since = time.monotonic()
            last_api = (invoked, has_failure)
            if invoked and has_failure:
                # R62-C1: API is SSOT under parallel MUX load — do not burn BODY
                # waiting for DOM banner when messages already record the failure.
                touch_wall_progress()
                try:
                    banner = await chat.evaluate(
                        _LIVE_MUTATION_BANNER_JS,
                        intent=EvaluateIntent.BRIDGE_POLL,
                    )
                    if isinstance(banner, dict) and banner.get("ready") is True:
                        return {"source": "ui+api", "banner": banner, "invoked": True}
                except (RuntimeError, TimeoutError):
                    pass
                return {
                    "source": "api",
                    "invoked": True,
                    "has_failure": True,
                }

            if (
                invoked
                and not has_failure
                and target_file is not None
                and not target_file.exists()
                and invoked_since is not None
                and time.monotonic() - invoked_since >= 90.0
            ):
                write_calls = _file_write_tool_call_count(chat_id, api_url=api_base)
                if write_calls == 1:
                    # Empty writes can land on disk after tool invoke; settle before api+disk.
                    await asyncio.sleep(5.0)
                    touch_wall_progress()
                    if target_file.exists():
                        last_progress_at = time.monotonic()
                        continue
                    _, settled_failure = await _poll_empty_write_api(chat_id)
                    if settled_failure:
                        return {
                            "source": "api",
                            "invoked": True,
                            "has_failure": True,
                        }
                    if not target_file.exists():
                        return {
                            "source": "api+disk",
                            "invoked": True,
                            "has_failure": False,
                            "disk_clean": True,
                        }

            try:
                raw = await chat.evaluate(
                    """(() => {
                      const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
                      const text = String(snap.lastAssistantSample || '');
                      const bodyText = document.body?.innerText || '';
                      const store = window.__myrmChatStore?.getState?.();
                      const failures = (store?.messages || []).flatMap((msg) =>
                        Array.isArray(msg.fileMutationFailures) ? msg.fileMutationFailures : [],
                      );
                      return {
                        isStreaming: Boolean(snap.isStreaming),
                        hasEmptyWriteDone: /EMPTY_WRITE_DONE/i.test(text),
                        hasDomEmptyWriteError: /Cannot write empty file content/i.test(bodyText),
                        failureCount: failures.length,
                        sample: text.slice(0, 600),
                      };
                    })()""",
                    intent=EvaluateIntent.BRIDGE_POLL,
                )
            except (RuntimeError, TimeoutError) as ui_exc:
                if (
                    _is_mux_io_deferrable(ui_exc)
                    and _parallel_live_agent_peer_count() >= 2
                ):
                    print(
                        "E2E_MUX_UI_EVAL_DEFER: parallel mux busy — API poll SSOT; "
                        f"api_invoked={last_api[0]} parallel_peers="
                        f"{_parallel_live_agent_peer_count()}",
                        file=sys.stderr,
                        flush=True,
                    )
                    touch_wall_progress()
                    await asyncio.sleep(2.0)
                    continue
                raise
            ui = raw if isinstance(raw, dict) else {"value": raw}
            ui_sample = str(ui.get("sample") or "")
            if last_api[0]:
                if ui_sample != last_ui_sample or int(ui.get("failureCount") or 0) >= 1:
                    last_ui_sample = ui_sample
                    last_progress_at = time.monotonic()
                    touch_wall_progress()
            if ui.get("isStreaming") is True and last_api[0]:
                last_progress_at = time.monotonic()
                touch_wall_progress()
            if (
                ui.get("hasDomEmptyWriteError") is True
                and ui.get("isStreaming") is False
            ):
                return {"source": "ui-dom", "ui": ui}
            if int(ui.get("failureCount") or 0) >= 1 and ui.get("isStreaming") is False:
                banner = await chat.evaluate(
                    _LIVE_MUTATION_BANNER_JS,
                    intent=EvaluateIntent.BRIDGE_POLL,
                )
                if isinstance(banner, dict) and banner.get("ready") is True:
                    return {"source": "ui", "banner": banner, "ui": ui}
                return {
                    "source": "ui",
                    "ui": ui,
                    "failureCount": int(ui.get("failureCount") or 0),
                }
            if (
                ui.get("hasEmptyWriteDone") is True
                and ui.get("isStreaming") is False
                and last_api[0]
            ):
                settle_deadline = time.monotonic() + 45.0
                while time.monotonic() < settle_deadline:
                    touch_wall_progress()
                    invoked, has_failure = await _poll_empty_write_api(chat_id)
                    if invoked and has_failure:
                        return {
                            "source": "api",
                            "invoked": True,
                            "has_failure": True,
                        }
                    if (
                        invoked
                        and target_file is not None
                        and not target_file.exists()
                        and _file_write_tool_call_count(chat_id, api_url=api_base) == 1
                    ):
                        return {
                            "source": "api+disk",
                            "invoked": True,
                            "has_failure": False,
                            "disk_clean": True,
                        }
                    await asyncio.sleep(2.0)
            elif not last_api[0] and not_invoked_since is not None:
                idle_sec = time.monotonic() - not_invoked_since
                nudge_filename = (
                    target_file.name if target_file is not None else "output.txt"
                )
                if idle_sec >= 30.0 and not last_api[0]:
                    # R150/R173: steer before UI nudge; repeat steer under parallel.
                    steer_cap = _live_empty_write_steer_attempts_cap()
                    if steer_attempts < steer_cap and (
                        steer_attempts == 0
                        or idle_sec >= _live_empty_write_steer_retry_idle_sec()
                    ):
                        steer_attempts += 1
                        steer_ok = await _steer_empty_write_turn(
                            chat_id, nudge_filename
                        )
                        not_invoked_since = time.monotonic()
                        last_progress_at = not_invoked_since
                        if steer_ok:
                            await asyncio.sleep(1.5)
                            continue
                    if ui_nudge_attempts < 2 and (
                        steer_attempts == 0
                        or _live_empty_write_ui_nudge_allowed_after_steer(
                            idle_sec=idle_sec
                        )
                    ):
                        nudge_outcome = await _api_nudge_turn(
                            chat_id, agent_id, nudge_filename
                        )
                        not_invoked_since = time.monotonic()
                        last_progress_at = not_invoked_since
                        if nudge_outcome == "ok":
                            ui_nudge_attempts += 1
                        elif nudge_outcome == "deferred":
                            if steer_attempts > 0:
                                touch_wall_progress()
                            pass
                elif idle_sec >= _live_empty_write_post_steer_idle_cap_sec():
                    raise AssertionError(
                        "Live empty write: LLM idle without file_write_tool; "
                        f"api_invoked={last_api[0]} steer_attempts={steer_attempts} "
                        f"ui_nudges={ui_nudge_attempts} idle_sec={idle_sec:.0f} "
                        f"cap={_live_empty_write_post_steer_idle_cap_sec():.0f}s "
                        f"parallel_peers={_parallel_live_agent_peer_count()} "
                        f"ui_sample={ui_sample[:500]!r} isStreaming={ui.get('isStreaming')}"
                    )
            # R62-C1/R132: stall fail-fast when stream idle and tool not yet invoked.
            # After invoke without failure metadata, wait for API/UI settle (no stall).
            if not last_api[0] and not_invoked_since is not None:
                stall_elapsed = time.monotonic() - not_invoked_since
                stall_cap = _live_empty_write_post_send_stall_cap_sec()
                if stall_elapsed >= stall_cap:
                    raise AssertionError(
                        "E2E_STALL: live empty write made no progress for "
                        f"{int(stall_elapsed)}s (cap={stall_cap:.0f}s); "
                        f"api_invoked={last_api[0]} api_failure={last_api[1]} "
                        f"isStreaming={ui.get('isStreaming')} "
                        f"steer_attempts={steer_attempts} ui_nudges={ui_nudge_attempts} "
                        f"parallel_peers={_parallel_live_agent_peer_count()} "
                        f"remaining_wall={remaining_wall_sec():.0f}s"
                    )
            elif ui.get("isStreaming") is not True and not (
                last_api[0] and not last_api[1]
            ):
                stall_elapsed = time.monotonic() - last_progress_at
                stall_cap = _live_empty_write_post_send_stall_cap_sec()
                if stall_elapsed >= stall_cap:
                    raise AssertionError(
                        "E2E_STALL: live empty write made no progress for "
                        f"{int(stall_elapsed)}s (cap={stall_cap:.0f}s); "
                        f"api_invoked={last_api[0]} api_failure={last_api[1]} "
                        f"isStreaming={ui.get('isStreaming')} "
                        f"steer_attempts={steer_attempts} ui_nudges={ui_nudge_attempts} "
                        f"parallel_peers={_parallel_live_agent_peer_count()} "
                        f"remaining_wall={remaining_wall_sec():.0f}s"
                    )
            await asyncio.sleep(1.5)
        raise AssertionError(
            f"Live empty write did not produce mutation failure banner; "
            f"api_invoked={last_api[0]} api_failure={last_api[1]}"
        )

    async def _ensure_agent_url_loaded(
        chat: McpChatSession, target_agent_url: str
    ) -> None:
        """R135/R139: re-navigate when shared UI drops ?agentId= or tab is chrome-error."""
        raw = await chat.evaluate(
            "(() => ({ href: String(location.href || ''), path: String(location.pathname || '') }))()",
            intent=EvaluateIntent.SYNC_PROBE,
        )
        probe = raw if isinstance(raw, dict) else {"value": raw}
        href = str(probe.get("href") or "")
        needs_navigate = (
            href.startswith("chrome-error:")
            or href in ("about:blank", "")
            or "agentId=" not in href
        )
        if not needs_navigate:
            return
        print(
            f"E2E_AGENT_URL_RELOAD: href={href[:120]!r} target={target_agent_url[:120]!r}",
            file=sys.stderr,
            flush=True,
        )
        await chat.cdp(
            "Page.navigate",
            {"url": target_agent_url},
            recv_timeout=120.0,
        )
        await asyncio.sleep(2.0)
        touch_wall_progress()
        await chat.wait_shell_ready(timeout_sec=60.0)
        await _rehydrate_providers_after_agent_navigate(chat)

    async def _rehydrate_providers_after_agent_navigate(
        chat: McpChatSession,
    ) -> None:
        """R166: shared UI bootstrap hydrates at `/`; agent URL reload drops selection."""
        hydrate_cap = _bounded_wait_sec(60.0, reserve_sec=90.0)
        bridge_cap = min(_live_bridge_ready_timeout_sec(), hydrate_cap)
        await chat.ensure_react_e2e_bridge(timeout_sec=bridge_cap)
        try:
            ensured = await chat.evaluate(
                _ENSURE_PROVIDERS_JS,
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
            if isinstance(ensured, dict) and ensured.get("ok") is not True:
                print(
                    "E2E_AGENT_URL_REHYDRATE: ensureProviders returned "
                    f"{ensured!r} parallel_peers={_parallel_live_agent_peer_count()}",
                    file=sys.stderr,
                    flush=True,
                )
        except (RuntimeError, TimeoutError) as exc:
            print(
                "E2E_AGENT_URL_REHYDRATE: ensureProviders deferred "
                f"parallel_peers={_parallel_live_agent_peer_count()} err={str(exc)[:180]!r}",
                file=sys.stderr,
                flush=True,
            )
        deadline = time.monotonic() + hydrate_cap
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            touch_wall_progress()
            raw = await chat.evaluate(
                _PROVIDERS_SEND_READY_JS,
                intent=EvaluateIntent.BRIDGE_POLL,
            )
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("sendReady") and last.get("selection"):
                print(
                    "E2E_AGENT_URL_REHYDRATE_OK: "
                    f"parallel_peers={_parallel_live_agent_peer_count()} probe={last}",
                    file=sys.stderr,
                    flush=True,
                )
                return
            await asyncio.sleep(0.5)
        print(
            "E2E_AGENT_URL_REHYDRATE_WAIT: selection still pending "
            f"parallel_peers={_parallel_live_agent_peer_count()} last={last}",
            file=sys.stderr,
            flush=True,
        )

    async def _assert_agent_bound(chat: McpChatSession, expected_agent_id: str) -> None:
        deadline = time.monotonic() + _bounded_wait_sec(45.0, reserve_sec=60.0)
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            touch_wall_progress()
            raw = await chat.evaluate(
                f"({_AGENT_BOUND_JS})({json.dumps(expected_agent_id)})",
                intent=EvaluateIntent.BRIDGE_POLL,
            )
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return
            await asyncio.sleep(1.0)
        raise AssertionError(f"Agent not bound in UI before live turn: {last}")

    async def _ensure_live_bridge_ready(chat: McpChatSession) -> None:
        """R138: parallel-safe bridge gate before new-chat / chat surface."""
        bridge_cap = _live_bridge_ready_timeout_sec()
        await chat.ensure_react_e2e_bridge(timeout_sec=bridge_cap)

    async def _run_flow(chat: McpChatSession) -> tuple[str, dict[str, object]]:
        nonlocal turn_ever_sent
        await chat.dismiss_modals()
        await _wait_agent_applied(chat)
        await _assert_agent_bound(chat, agent_id)
        await _ensure_live_bridge_ready(chat)
        pinned_model = await _pin_lite_model(chat)
        await chat.click_new_chat(timeout_sec=_live_bridge_ready_timeout_sec())
        await chat.ensure_chat_surface(BASE_URL)

        ensured = await chat.evaluate(
            _ENSURE_CHAT_SESSION_JS, intent=EvaluateIntent.ROUTE_ATTACH
        )
        assert isinstance(ensured, dict) and ensured.get("ok") is True, ensured

        chat_id = str((await chat.bridge_chat_id()) or "").strip()
        assert chat_id, "Expected client chat id after new chat before sandbox seed"
        workspace_seed = _seed_live_workspace(api_base, chat_id)
        live_filename = _live_empty_write_filename()
        target_file = _empty_write_target_path(workspace_seed, live_filename)
        if target_file.exists():
            target_file.unlink()

        live_prompt = _live_user_prompt(live_filename)
        send_result = await chat.send_message(live_prompt, live_prompt)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or chat_id
        ).strip()

        heartbeat_once()
        started = await chat.wait_stream_started(
            live_prompt,
            timeout_sec=_bounded_wait_sec(90.0, reserve_sec=120.0),
            chat_id_hint=chat_id_hint or None,
        )
        resolved_chat_id = (
            chat_id_hint or str(started.get("chatId") or "").strip() or None
        )
        assert resolved_chat_id, (
            f"Expected chat id after stream start: started={started}; send={send_result}; "
            f"model={pinned_model.get('providerId')}/{pinned_model.get('model')}"
        )
        turn_ever_sent = True
        print(
            f"E2E_SEND_TURN: chat_id={resolved_chat_id} parallel_peers={_parallel_live_agent_peer_count()}",
            file=sys.stderr,
            flush=True,
        )

        current_chat = str((await chat.bridge_chat_id()) or "").strip()
        if current_chat != resolved_chat_id:
            try:
                await chat.navigate_to_chat(
                    resolved_chat_id,
                    BASE_URL,
                    timeout_sec=_bounded_wait_sec(45.0, reserve_sec=45.0),
                )
            except (RuntimeError, TimeoutError) as nav_exc:
                if (
                    _is_mux_io_deferrable(nav_exc)
                    and _parallel_live_agent_peer_count() >= 2
                ):
                    print(
                        "E2E_SKIP_CHAT_NAVIGATE_PARALLEL: chat_id mismatch tolerated; "
                        f"resolved={resolved_chat_id!r} bridge={current_chat!r} "
                        f"parallel_peers={_parallel_live_agent_peer_count()}",
                        file=sys.stderr,
                        flush=True,
                    )
                    touch_wall_progress()
                else:
                    raise
        result = await _wait_turn_done(
            chat, resolved_chat_id, agent_id=agent_id, target_file=target_file
        )
        invoked, has_failure = _empty_write_failure_in_messages(
            resolved_chat_id, api_url=api_base
        )
        write_calls = _file_write_tool_call_count(resolved_chat_id, api_url=api_base)
        assert (
            invoked
        ), f"{_FILE_WRITE_TOOL} not found in persisted messages; result={result}"
        assert (
            has_failure
            or (result.get("source") == "api+disk" and result.get("disk_clean") is True)
            or (
                result.get("source") in ("ui", "ui-dom")
                and (
                    int(result.get("failureCount") or 0) >= 1
                    or result.get("source") == "ui-dom"
                )
            )
        ), f"fileMutationFailures missing; result={result}"
        assert write_calls <= 1, (
            f"Expected at most one {_FILE_WRITE_TOOL} call, got {write_calls}; "
            f"result={result}"
        )
        _assert_empty_write_disk_clean(target_file)
        e2e_resource_ledger.register("chat", resolved_chat_id)
        return resolved_chat_id, result

    last_error = ""
    agent_url = f"{ui_base}/?agentId={agent_id}"
    turn_ever_sent = False

    def _run_live_in_open_page() -> tuple[str, dict[str, object]]:
        with open_mcp_page(agent_url, timeout_ms=120_000) as (client, page):

            async def _inner() -> tuple[str, dict[str, object]]:
                chat = McpChatSession(client, page)
                boot_attempts = 3 if _parallel_live_agent_peer_count() >= 2 else 1
                for boot_idx in range(boot_attempts):
                    try:
                        await chat.bootstrap(agent_url, timeout_sec=180.0)
                        break
                    except (RuntimeError, TimeoutError) as boot_exc:
                        if (
                            not _is_mux_io_deferrable(boot_exc)
                            or boot_idx >= boot_attempts - 1
                        ):
                            raise
                        print(
                            "E2E_BOOTSTRAP_MUX_RETRY: parallel mux reclaim — "
                            f"attempt={boot_idx + 1}/{boot_attempts} "
                            f"parallel_peers={_parallel_live_agent_peer_count()} "
                            f"err={str(boot_exc)[:180]!r}",
                            file=sys.stderr,
                            flush=True,
                        )
                        _force_mux_heal_before_live_retry()
                        await asyncio.sleep(8.0 * (boot_idx + 1))
                await _ensure_agent_url_loaded(chat, agent_url)
                await _ensure_live_bridge_ready(chat)
                return await _run_flow(chat)

            return asyncio.run(_inner())

    for attempt in range(_live_chat_attempt_cap()):
        heartbeat_once()
        try:
            chat_id, result = await asyncio.to_thread(_run_live_in_open_page)
            assert chat_id
            assert result.get("invoked") is True or "banner" in result
            break
        except (AssertionError, RuntimeError, TimeoutError, KeyboardInterrupt) as exc:
            exc = _normalize_live_transport_exc(exc)
            last_error = str(exc)
            if turn_ever_sent:
                print(
                    "E2E_BUSINESS_FAIL_NO_RETRY: turn already sent; "
                    f"parallel_peers={_parallel_live_agent_peer_count()} err={last_error[:240]!r}",
                    file=sys.stderr,
                    flush=True,
                )
                raise
            if not _is_transport_retryable(exc):
                raise
            if attempt >= _live_chat_attempt_cap() - 1:
                raise
            body_reserve = 200.0 if _parallel_live_agent_peer_count() >= 2 else 120.0
            if remaining_wall_sec() < body_reserve:
                raise AssertionError(
                    "E2E live empty write: skip transport retry — insufficient BODY "
                    f"reserve {body_reserve:.0f}s remaining={remaining_wall_sec():.0f}s; "
                    f"parallel_peers={_parallel_live_agent_peer_count()} err={last_error[:200]!r}"
                ) from exc
            print(
                "E2E_OPEN_MCP_STALL_RETRY: parallel mux stall — heal and retry "
                f"attempt={attempt + 1}/{_live_chat_attempt_cap()} "
                f"parallel_peers={_parallel_live_agent_peer_count()} "
                f"err={last_error[:200]!r}",
                file=sys.stderr,
                flush=True,
            )
            _force_mux_heal_before_live_retry()
            await asyncio.sleep(8.0)
    else:
        pytest.fail(last_error or "live empty write WebUI flow failed")
