"""Chrome E2E: smart-routing tier is emitted and surfaced in the real WebUI.

Real-user flow: configure providers via the config API, open the WebUI in a
real Chrome, send two turns through the chat input, and assert the assistant
message carries the correct routing tier (greeting → simple, debug/traceback
→ standard). This exercises the full real pipeline: frontend message request →
server converter → real harness route_task (no mocks) → SSE ROUTING_DECISION →
Zustand store routingTier → UI tier badge.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    config_write_mutex,
    fetch_config_value,
    get_e2e_api_url,
    get_e2e_ui_url,
    put_config_value,
    wait_e2e_provider_ready,
)
from cdp_chat.ui import chat_id_from_path  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_mcp_e2e import open_mcp_page_async
from tests.support.e2e_provider_seed import (
    infer_provider_id,
    strip_provider_prefix,
    upsert_provider,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once
from tests.support.test_secrets import load_test_secrets

TURN_WAIT_SEC = 180.0
SIMPLE_PROMPT = "hello"
DEBUG_PROMPT = (
    "请帮我 debug 这个 Python 报错：TypeError: unsupported operand type(s) "
    "for +: 'int' and 'str'，问题出现在数据处理管线的第三行，我需要定位根因并修复它。"
)

_PIN_BASIC_PRIMARY_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinBasicModelForE2e) {
    return { ok: false, err: 'no pinBasicModelForE2e' };
  }
  const sel = await bridge.pinBasicModelForE2e();
  return { ok: true, selection: sel };
})()"""

_GET_LIGHT_SELECTION_JS = """(() => {
  try {
    const debug = window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null;
    return { ok: true, debug };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_ARM_SSE_RECORDER_JS = """(() => {
  if (window.__MYRM_SSE_LOG__) return { ok: true, already: true };
  const events = [];
  window.__MYRM_SSE_LOG__ = events;
  const orig = window.__MYRM_E2E_RECORD_SSE__;
  if (typeof orig !== 'function') return { ok: false, err: 'no frontend recorder' };
  window.__MYRM_E2E_RECORD_SSE__ = (type, messageId, data) => {
    const rec = { type, messageId: messageId ?? null };
    if (data !== undefined) rec.data = data;
    if (type === 'routing_decision') {
      const store = window.__myrmChatStore?.getState?.();
      rec.assistantCount = (store?.messages || []).filter((m) => m.role === 'assistant').length;
      rec.snapshot = (store?.messages || []).slice(-2).map((m) => ({ role: m.role, id: m.messageId, tier: m.routingTier ?? null }));
      const after = (ms, id) => setTimeout(() => {
        const s = window.__myrmChatStore?.getState?.();
        rec.post = { ms, msgs: (s?.messages || []).slice(-2).map((m) => ({ role: m.role, id: m.messageId, tier: m.routingTier ?? null, keys: Object.keys(m) })) };;
      }, ms);
      after(0, id);
      after(1000, id);
    }
    events.push(rec);
    if (orig) orig(type, messageId, data);
  };
  return { ok: true, captured: 0 };
})()"""

_READ_SSE_LOG_JS = """(() => ({
  events: (window.__MYRM_SSE_LOG__ || []).slice(-40),
}))()"""

_LATEST_ASSISTANT_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  const roles = msgs.map((m) => m.role || m.type || '?');
  const all = msgs.map((m, i) => ({
    i,
    role: m.role || m.type || '?',
    tier: m.routingTier || null,
    modelTier: m.modelTier || null,
    model: m.modelName || m.model || null,
    msgId: m.messageId || m.id || null,
    content: String(m.content || m.text || '').slice(0, 40),
  }));
  for (let i = msgs.length - 1; i >= 0; i -= 1) {
    const msg = msgs[i];
    if (msg.role !== 'assistant' && msg.type !== 'assistant') continue;
    return {
      ready: true,
      routingTier: msg.routingTier || null,
      modelTier: msg.modelTier || null,
      modelName: msg.modelName || msg.model || null,
      content: String(msg.content || msg.text || '').slice(0, 100),
      msg_count: msgs.length,
      roles: roles.slice(-5),
      all: all.slice(-8),
      keys: Object.keys(msg),
      meta: msg.metadata ?? null,
    };
  }
  return {
    ready: false,
    msg_count: msgs.length,
    roles: roles.slice(-5),
    storePresent: !!window.__myrmChatStore,
    all: all.slice(-8),
  };
})()"""

_TIER_BADGE_JS = """(() => {
  const labels = Array.from(document.querySelectorAll('span,div'))
    .map((el) => (el.textContent || '').trim())
    .filter((t) => /^(Light|Standard|Reasoning|轻量|常规|推理)$/.test(t));
  return { found: labels.length > 0, labels: labels.slice(0, 5) };
})()"""

_HOVER_TOKEN_BTN_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((b) => {
    const label = b.getAttribute('aria-label') || '';
    return /token|context/i.test(label);
  });
  if (!btn) return { ok: false, err: 'no token button' };
  const opts = { bubbles: true, cancelable: true };
  btn.dispatchEvent(new PointerEvent('pointerover', opts));
  btn.dispatchEvent(new MouseEvent('mouseover', opts));
  btn.dispatchEvent(new MouseEvent('mouseenter', opts));
  return { ok: true, aria: btn.getAttribute('aria-label') };
})()"""


def _configure_smart_routing_providers(api_url: str, *, verify: bool = False) -> dict[str, object]:
    secrets = load_test_secrets()
    basic_model = secrets.basic_model
    lite_model = secrets.lite_model
    assert basic_model and secrets.basic_api_key, "BASIC_* missing in .env.test"
    assert lite_model and secrets.lite_api_key, "LITE_* missing in .env.test"

    basic_provider_id = infer_provider_id(basic_model)
    lite_provider_id = infer_provider_id(lite_model)
    lite_model_id = strip_provider_prefix(lite_model)
    basic_model_id = strip_provider_prefix(basic_model)

    current = fetch_config_value("providers", api_url=api_url)
    providers = current.get("providers")
    provider_list = providers if isinstance(providers, list) else []
    provider_list = upsert_provider(
        [p for p in provider_list if isinstance(p, dict)],
        provider_id=basic_provider_id,
        model_id=basic_model_id,
        api_url=secrets.basic_base_url,
        api_key=secrets.basic_api_key,
    )
    provider_list = upsert_provider(
        provider_list,
        provider_id=lite_provider_id,
        model_id=lite_model_id,
        api_url=secrets.lite_base_url,
        api_key=secrets.lite_api_key,
        merge_models=True,
    )

    base_primary = {"providerId": basic_provider_id, "model": basic_model_id}
    lite_primary = {"providerId": lite_provider_id, "model": lite_model_id}
    dmc = dict(current.get("defaultModelConfig") or {})
    dmc["baseModel"] = {
        "primary": base_primary,
        "fallback": dict(lite_primary),
        "temperature": 0.7,
        "modelKwargs": {},
    }
    dmc["liteModel"] = {
        "primary": dict(lite_primary),
        "fallback": None,
        "temperature": 0.7,
    }
    dmc["routingConfig"] = {
        "enabled": True,
        "lightModel": {
            "primary": dict(lite_primary),
            "fallback": None,
            "modelKwargs": {},
        },
        "reasoningModel": {"primary": None, "fallback": None, "modelKwargs": {}},
    }

    merged: dict[str, object] = {
        **current,
        "providers": provider_list,
        "defaultModelConfig": dmc,
        "customModelInfo": current.get("customModelInfo") or {},
    }
    put_config_value("providers", merged, api_url=api_url)
    if verify:
        _assert_routing_seed_effective(api_url, lite_provider_id, lite_model_id)
    return merged


def _assert_routing_seed_effective(api_url: str, lite_provider_id: str, lite_model_id: str) -> None:
    recheck = fetch_config_value("providers", api_url=api_url)
    dmc = recheck.get("defaultModelConfig")
    assert isinstance(dmc, dict), recheck
    routing_cfg = dmc.get("routingConfig")
    assert isinstance(routing_cfg, dict) and routing_cfg.get("enabled") is True, recheck
    light_primary = routing_cfg.get("lightModel", {}).get("primary") if isinstance(routing_cfg, dict) else None
    assert isinstance(light_primary, dict), recheck
    assert light_primary.get("providerId") == lite_provider_id and light_primary.get("model") == lite_model_id, recheck


def _base_url() -> str:
    return get_e2e_ui_url().rstrip("/")


async def _dump_sse_log(chat: McpChatSession) -> None:
    try:
        raw = await chat.evaluate(
            _READ_SSE_LOG_JS,
            intent=EvaluateIntent.SYNC_PROBE,
        )
        state = raw if isinstance(raw, dict) else json.loads(str(raw))
        events = state.get("events")
        print(f"[E2E_SSE_LOG] events={len(events) if isinstance(events, list) else '?'}", file=sys.stderr, flush=True)
        for ev in events if isinstance(events, list) else []:
            print(f"[E2E_SSE_LOG] {ev}", file=sys.stderr, flush=True)
    except Exception as exc:  # pragma: no cover - diagnostic only
        print(f"[E2E_SSE_LOG] failed: {exc}", file=sys.stderr, flush=True)


def _dump_backend_routing_log(api_url: str) -> None:
    """Dump backend routing evidence (routing_decision / routing_tier / route_task)."""
    try:
        from cdp_chat.ui import backend_log_path

        path = backend_log_path(api_url=api_url)
        if not path.exists():
            print(f"[E2E_ROUTING_LOG] no backend log at {path}", file=sys.stderr, flush=True)
            return
        size = path.stat().st_size
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(max(0, size - 600_000))
            tail = fh.read()
        lines = [
            line
            for line in tail.splitlines()
            if any(
                kw in line
                for kw in (
                    "routing_decision",
                    "routing_tier",
                    "route_task",
                    "ROUTING_DECISION",
                    "routing",
                    "smart_routing",
                )
            )
        ]
        print(
            f"[E2E_ROUTING_LOG] path={path} matched={len(lines)}",
            file=sys.stderr,
            flush=True,
        )
        for line in lines[-40:]:
            print(f"[E2E_ROUTING_LOG] {line}", file=sys.stderr, flush=True)
    except Exception as exc:  # pragma: no cover - diagnostic only
        print(f"[E2E_ROUTING_LOG] failed to dump: {exc}", file=sys.stderr, flush=True)


async def _wait_tier(chat: McpChatSession, expected: str) -> dict[str, object]:
    deadline = time.monotonic() + TURN_WAIT_SEC
    last_state: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = await chat.evaluate(
            _LATEST_ASSISTANT_JS,
            intent=EvaluateIntent.SYNC_PROBE,
        )
        state = raw if isinstance(raw, dict) else json.loads(str(raw))
        bridge = await chat._bridge_turn_snapshot()
        streaming = isinstance(bridge, dict) and bridge.get("isStreaming") is True
        last_state = state
        if (
            state.get("ready") is True
            and state.get("routingTier") == expected
            and not streaming
            and str(state.get("content") or "").strip()
        ):
            return state
        await asyncio.sleep(0.5)
    print(
        "[E2E_STORE_STATE] " + json.dumps(last_state, indent=2, default=str),
        file=sys.stderr,
        flush=True,
    )
    return last_state  # type: ignore[return-value]


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_smart_routing_tier_surfaced_in_webui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Greeting routes simple; debug/traceback routes standard — badge visible."""
    api_url = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_url, timeout_sec=120.0):
        pytest.fail(
            "Provider config not ready for live smart-routing E2E — run via ./myrm test -m chrome_e2e after ./myrm ready --chrome"
        )

    backup = fetch_config_value("providers", api_url=api_url)
    try:
        # R2: the global providers config is shared by every chrome_e2e session.
        # The whole "seed → verify → run flow" window must hold the per-key
        # mutex so a parallel peer cannot overwrite our routing seed mid-flow.
        # This replaces the fragile re-seed-before-every-send mitigation.
        # The wait window mirrors the session-queue ceiling so a peer that is
        # mid-flow simply serializes; it never times out under normal parallel
        # load. Timeout is an honest serialization failure (log + fail-fast).
        with config_write_mutex("providers", wait_sec=900.0):
            _configure_smart_routing_providers(api_url, verify=True)
            if not wait_e2e_provider_ready(api_url=api_url, timeout_sec=60.0):
                pytest.fail("Provider readiness failed after smart-routing seed")

            async def run_flow(chat: McpChatSession) -> None:
                ui_base = _base_url()
                await chat.bootstrap(ui_base, navigate=False, timeout_sec=180.0)
                await chat.click_new_chat()
                await chat.evaluate(
                    _ARM_SSE_RECORDER_JS,
                    intent=EvaluateIntent.AGENT_SUBMIT,
                )

                pin_raw = await chat.evaluate(
                    _PIN_BASIC_PRIMARY_JS,
                    intent=EvaluateIntent.AGENT_SUBMIT,
                )
                pin_state = pin_raw if isinstance(pin_raw, dict) else json.loads(str(pin_raw))
                assert pin_state.get("ok") is True, pin_state
                selection = pin_state.get("selection")
                assert isinstance(selection, dict), pin_state
                assert str(selection.get("model") or ""), pin_state
                light_probe = await chat.evaluate(
                    _GET_LIGHT_SELECTION_JS,
                    intent=EvaluateIntent.SYNC_PROBE,
                )
                print(
                    f"[E2E_LIGHT_SELECTION] {light_probe}",
                    file=sys.stderr,
                    flush=True,
                )

                send_result = await chat.send_message(
                    SIMPLE_PROMPT,
                    SIMPLE_PROMPT,
                )
                chat_id = (
                    str(send_result.get("started", {}).get("chatId") or send_result.get("submit", {}).get("chatId") or "").strip()
                    or None
                )

                simple_state = await _wait_tier(chat, "simple")
                if simple_state.get("routingTier") != "simple":
                    _dump_backend_routing_log(api_url)
                    await _dump_sse_log(chat)
                assert simple_state.get("routingTier") == "simple", simple_state
                heartbeat_once()

                await chat.evaluate(
                    _PIN_BASIC_PRIMARY_JS,
                    intent=EvaluateIntent.AGENT_SUBMIT,
                )
                await chat.send_message(
                    DEBUG_PROMPT,
                    DEBUG_PROMPT,
                )
                standard_state = await _wait_tier(chat, "standard")
                if standard_state.get("routingTier") != "standard":
                    _dump_backend_routing_log(api_url)
                    await _dump_sse_log(chat)
                assert standard_state.get("routingTier") == "standard", standard_state

                # 档位 badge 位于 token 用量 tooltip 内（默认隐藏）——hover 触发后轮询可见。
                hover = await chat.evaluate(
                    _HOVER_TOKEN_BTN_JS,
                    intent=EvaluateIntent.AGENT_SUBMIT,
                )
                hover_state = hover if isinstance(hover, dict) else json.loads(str(hover))
                assert hover_state.get("ok") is True, hover_state
                deadline = time.monotonic() + 10.0
                badge_state: dict[str, object] = {}
                while time.monotonic() < deadline:
                    badge = await chat.evaluate(
                        _TIER_BADGE_JS,
                        intent=EvaluateIntent.SYNC_PROBE,
                    )
                    badge_state = badge if isinstance(badge, dict) else json.loads(str(badge))
                    if badge_state.get("found") is True:
                        break
                    await asyncio.sleep(0.5)
                assert badge_state.get("found") is True, badge_state

                resolved_chat_id = chat_id
                if not resolved_chat_id:
                    after = await chat.main_state(DEBUG_PROMPT, intent=EvaluateIntent.BRIDGE_POLL)
                    href = str(after.get("url") or "")
                    resolved_chat_id = chat_id_from_path(href.split("?", 1)[0])
                if resolved_chat_id:
                    e2e_resource_ledger.register("chat", resolved_chat_id)

            page_session = await open_mcp_page_async(
                _base_url(),
                request_timeout_sec=180.0,
                timeout_ms=120_000,
            )
            try:
                await run_flow(McpChatSession(page_session.client, page_session.page))
            finally:
                await page_session.aclose()
    finally:
        if isinstance(backup, dict) and backup:
            put_config_value("providers", backup, api_url=api_url)
