"""Chrome E2E: migration post-import readiness SSE toast on first chat."""

from __future__ import annotations

import json

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

_AGENT_PROMPT = "Hello after migration import"

_BRIDGE_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[data-testid="app-layout"]') &&
    !!window.__MYRM_E2E_CHAT__ &&
    typeof window.__MYRM_E2E_CHAT__.sendChatMessage === 'function',
}))()"""

_MIGRATION_GAP_TOAST_PATTERN = (
    r"MCP servers were imported|MCP 已导入|migration follow-ups|待完成项|/settings/mcp"
)


def _seed_migration_readiness(*, variant: str = "mcp_warning") -> dict[str, str]:
    api_base = get_e2e_api_url()
    payload = http_json(
        "POST",
        f"{api_base}/api/v1/memory/test/seed-migration-readiness-fixture?variant={variant}",
    )
    assert isinstance(payload, dict)
    return {str(key): str(value) for key, value in payload.items()}


def _set_anchor_js(seed: dict[str, str]) -> str:
    seed_json = json.dumps(seed)
    return f"""(() => {{
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
    }})()"""


def _send_and_collect_gap_js(prompt: str) -> str:
    prompt_json = json.dumps(prompt)
    gap_pattern_json = json.dumps(_MIGRATION_GAP_TOAST_PATTERN)
    return f"""(async () => {{
      const bridge = window.__MYRM_E2E_CHAT__;
      if (!bridge) return {{ ok: false, err: 'no-bridge' }};
      bridge.abortActiveStream?.();
      bridge.releaseActiveStreamForApiResume?.();
      bridge.clearSseSnapshot?.();
      const baseline = bridge.turnSnapshot?.().userCount ?? 0;
      if (typeof bridge.sendChatMessage !== 'function') {{
        return {{ ok: false, err: 'no-sendChatMessage' }};
      }}
      const gapPattern = new RegExp({gap_pattern_json}, 'i');
      const sendPromise = bridge.sendChatMessage({prompt_json}, {{
        baselineUserCount: baseline,
        preserveActionMode: true,
      }}).then(
        (value) => value,
        (error) => ({{ ok: false, err: String(error) }}),
      );
      const deadline = Date.now() + 90000;
      let bestMigrationToast = 0;
      let bestSse = [];
      while (Date.now() < deadline) {{
        const toastNodes = Array.from(
          document.querySelectorAll('[data-sonner-toast], [data-sonner-toaster] [data-sonner-toast]'),
        );
        const texts = toastNodes.map((node) => (node.textContent || '').trim()).filter(Boolean);
        bestMigrationToast = Math.max(
          bestMigrationToast,
          texts.filter((t) => gapPattern.test(t)).length,
        );
        const sse = bridge.sseSnapshot?.() ?? [];
        if (Array.isArray(sse)) {{
          bestSse = sse;
        }}
        if (bestMigrationToast >= 1 || bestSse.includes('capability_gap')) {{
          const sendResult = await Promise.race([
            sendPromise,
            new Promise((resolve) => setTimeout(() => resolve({{ ok: true, pending: true }}), 0)),
          ]);
          return {{
            ok: true,
            sendResult,
            migrationToastCount: bestMigrationToast,
            sseEvents: bestSse,
          }};
        }}
        await new Promise((resolve) => setTimeout(resolve, 400));
      }}
      const sendResult = await Promise.race([
        sendPromise,
        new Promise((resolve) => setTimeout(() => resolve({{ ok: false, err: 'send-timeout' }}), 0)),
      ]);
      return {{
        ok: false,
        err: 'migration-gap-timeout',
        sendResult,
        migrationToastCount: bestMigrationToast,
        sseEvents: bestSse,
      }};
    }})()"""


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_migration_readiness_gap_shows_sse_toast_on_first_chat() -> None:
    """First chat after migration anchor must show MCP readiness toast via capability_gap SSE."""

    from app.services.agent.stream_session.entitlement_gap_preflight import (
        reset_capability_gap_emission_tracker,
    )

    reset_capability_gap_emission_tracker()

    api_base = get_e2e_api_url()
    seed = _seed_migration_readiness(variant="mcp_warning")
    prepare_e2e_ui_session(api_base)
    warm_ui_route(seed["chat_ui_path"])

    ui_url = get_e2e_ui_url()
    chat_url = f"{ui_url}{seed['chat_ui_path']}"

    with open_mcp_page(chat_url, request_timeout_sec=180.0) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=120.0)

        anchor_set = client.evaluate(page, _set_anchor_js(seed), timeout_sec=15.0)
        assert isinstance(anchor_set, dict) and anchor_set.get("ok") is True, anchor_set

        result = client.evaluate(
            page,
            _send_and_collect_gap_js(_AGENT_PROMPT),
            timeout_sec=150.0,
        )
        assert isinstance(result, dict), result
        migration_toast = int(result.get("migrationToastCount") or 0)
        sse_events = result.get("sseEvents")
        best_sse = list(sse_events) if isinstance(sse_events, list) else []
        assert result.get("ok") is True, result
        assert migration_toast >= 1 or "capability_gap" in best_sse, (
            f"expected migration readiness toast or capability_gap SSE; result={result!r}; seed={seed!r}"
        )
