"""Chrome E2E: migration post-import readiness SSE toast on first chat."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    WAIT_WORKSPACE_STREAM_JS,
    _e2e_api_urlopen,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from chrome_mcp_client import ChromeMcpClient  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import prepare_e2e_ui_session, warm_ui_route  # noqa: E402
from tests.support.e2e_runtime_guard import (
    E2EResourceLedger,
    heartbeat_e2e_lease,
)  # noqa: E402

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
_AGENT_PROMPT = "Hello after migration import"

_WAIT_CHAT_IDLE_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  bridge.abortActiveStream?.();
  bridge.releaseActiveStreamForApiResume?.();
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const turn = bridge.turnSnapshot?.() ?? {};
    if (!turn.isStreaming) {
      return { ok: true, turn };
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return { ok: false, err: 'chat-still-streaming', turn: bridge.turnSnapshot?.() ?? null };
})()"""

_MIGRATION_GAP_TOAST_PATTERN = (
    r"MCP servers were imported|MCP 已导入|migration follow-ups|待完成项|/settings/mcp"
)


async def _open_chat_page_with_retry(
    client: ChromeMcpClient,
    chat_url: str,
    *,
    attempts: int = 4,
) -> object:
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        if attempt > 0:
            await asyncio.sleep(2.0 * attempt)
        try:
            return await asyncio.to_thread(
                client.new_page,
                chat_url,
                timeout_ms=120_000,
            )
        except RuntimeError as exc:
            last_exc = exc
            message = str(exc).lower()
            if "timed out" not in message and "mux" not in message:
                raise
    assert last_exc is not None
    raise last_exc


def _seed_migration_readiness(
    api_base: str, *, variant: str = "mcp_warning"
) -> dict[str, str]:
    url = (
        f"{api_base.rstrip('/')}/api/v1/memory/test/seed-migration-readiness-fixture"
        f"?variant={variant}"
    )
    req = urllib.request.Request(url, method="POST")  # noqa: S310
    with _e2e_api_urlopen(req, timeout_sec=60.0) as resp:  # noqa: S310
        payload = json.loads(resp.read())  # type: ignore[union-attr]
    if not isinstance(payload, dict):
        raise AssertionError(f"Unexpected seed payload: {payload!r}")
    return {str(key): str(value) for key, value in payload.items()}


def _count_migration_toasts_js() -> str:
    return f"""(() => {{
      const toastNodes = Array.from(
        document.querySelectorAll('[data-sonner-toast], [data-sonner-toaster] [data-sonner-toast]'),
      );
      const texts = toastNodes.map((node) => (node.textContent || '').trim()).filter(Boolean);
      const gapPattern = /{_MIGRATION_GAP_TOAST_PATTERN}/i;
      const sseEvents = window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? [];
      return {{
        count: toastNodes.length,
        texts,
        migrationToastCount: texts.filter((t) => gapPattern.test(t)).length,
        sseEvents,
      }};
    }})()"""


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_migration_readiness_gap_shows_sse_toast_on_first_chat(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """First chat after migration anchor must show MCP readiness toast via capability_gap SSE."""

    from app.services.agent.stream_session.entitlement_gap_preflight import (
        reset_capability_gap_emission_tracker,
    )

    reset_capability_gap_emission_tracker()

    api_base = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_base):
        pytest.fail("Provider config not ready for migration readiness Chrome E2E")

    seed = _seed_migration_readiness(api_base, variant="mcp_warning")
    prepare_e2e_ui_session(api_base)
    warm_ui_route(seed["chat_ui_path"])
    wall_deadline = time.monotonic() + 480.0
    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        chat_url = f"{BASE_URL}{seed['chat_ui_path']}"
        page = await _open_chat_page_with_retry(client, chat_url)
        chat = McpChatSession(client, page)
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)

        seed_json = json.dumps(seed)
        anchor_set = await chat.evaluate(
            f"""(() => {{
              const seed = {seed_json};
              const key = 'myrm:migration-readiness-anchor';
              localStorage.setItem(
                key,
                JSON.stringify({{
                  importBatchId: seed.import_batch_id,
                  readinessStatus: seed.readiness_status,
                  targetAgentId: seed.target_agent_id,
                  queuedAt: new Date().toISOString(),
                }}),
              );
              return {{ ok: true, key, raw: localStorage.getItem(key) }};
            }})()""",
            await_promise=False,
            recv_timeout=15.0,
        )
        assert isinstance(anchor_set, dict) and anchor_set.get("ok") is True, anchor_set

        idle = await chat.evaluate(
            _WAIT_CHAT_IDLE_JS,
            await_promise=True,
            recv_timeout=20.0,
        )
        assert isinstance(idle, dict) and idle.get("ok") is True, idle

        workspace_ready = await chat.evaluate(
            WAIT_WORKSPACE_STREAM_JS,
            await_promise=True,
            recv_timeout=45.0,
        )
        assert (
            isinstance(workspace_ready, dict) and workspace_ready.get("ok") is True
        ), workspace_ready

        send = await chat.evaluate(
            f"""(async () => {{
              const prompt = {json.dumps(_AGENT_PROMPT)};
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge) return {{ ok: false, err: 'no-bridge' }};
              bridge.clearSseSnapshot?.();
              const baseline = bridge.turnSnapshot?.().userCount ?? 0;
              if (typeof bridge.sendChatMessage !== 'function') {{
                return {{ ok: false, err: 'no-sendChatMessage' }};
              }}
              const result = await bridge.sendChatMessage(prompt, {{
                baselineUserCount: baseline,
                preserveActionMode: true,
              }});
              return {{ ok: !!result?.ok, result }};
            }})()""",
            await_promise=True,
            recv_timeout=120.0,
        )
        assert isinstance(send, dict), send

        best_migration_toast = 0
        best_sse: list[str] = []
        deadline = min(time.monotonic() + 60.0, wall_deadline)
        while time.monotonic() < deadline:
            snap = await chat.evaluate(
                _count_migration_toasts_js(),
                await_promise=False,
                recv_timeout=12.0,
            )
            if isinstance(snap, dict):
                best_migration_toast = max(
                    best_migration_toast,
                    int(snap.get("migrationToastCount") or 0),
                )
                sse = snap.get("sseEvents")
                if isinstance(sse, list):
                    best_sse = list(sse)
                if best_migration_toast >= 1 or "capability_gap" in best_sse:
                    break
            await asyncio.sleep(0.4)

        assert best_migration_toast >= 1 or "capability_gap" in best_sse, (
            f"expected migration readiness toast or capability_gap SSE; "
            f"toastCount={best_migration_toast}; sse={best_sse!r}; send={send!r}; seed={seed!r}"
        )
    finally:
        await asyncio.to_thread(client.close)
        heartbeat_e2e_lease()
