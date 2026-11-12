"""Wait for the workflow plan card and confirm the plan in the UI or through the API."""

from __future__ import annotations

import time

from cdp_chat.support import get_e2e_api_url, get_e2e_ui_url
from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.orchestrator import touch_wall_progress

from .api import http_json
from .bridge import wait_for_react_e2e_bridge
from .open_page import _ensure_orchestrator_shared_ui_session
from .parallel_load import _parallel_chrome_e2e_active
from .plan_api import (
    _dw_unattended_enabled,
    _messages_from_api_payload,
    _plan_confirm_state_from_messages,
    _post_plan_confirm_via_api,
    _resolve_dw_stream_message_id,
    _wait_for_yolo_dw_plan_skip,
)
from .probe_result import _coerce_evaluate_result

_WORKFLOW_PLAN_CARD_JS = """(() => {
  const text = document.body?.innerText || '';
  const planRoot = document.querySelector('[data-testid="dynamic-workflow-plan-card"]');
  const runBtn = document.querySelector('[data-testid="dynamic-workflow-plan-run"]');
  const hasTitle = Boolean(planRoot) || /Dynamic Workflow Plan|动态工作流计划|ダイナミックワークフロープラン/i.test(text);
  const buttons = [...document.querySelectorAll('button')];
  const hasRun = Boolean(runBtn) || buttons.some((btn) =>
    /Run Workflow|运行工作流|執行工作流|ワークフローを実行/i.test((btn.textContent || '').trim()),
  );
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const apiBase = window.__MYRM_E2E_API_BASE__ ?? window.__MYRM_E2E_RUNTIME__?.apiBase ?? null;
  return {
    ready: hasTitle && hasRun,
    hasTitle,
    hasRun,
    hasPlanRoot: Boolean(planRoot),
    hasAppLayout: Boolean(document.querySelector('[data-testid="app-layout"]')),
    isStreaming: snap.isStreaming === true,
    userCount: snap.userCount ?? 0,
    lastAssistantSample: (snap.lastAssistantSample ?? '').slice(0, 240),
    apiBase,
    bodyLength: text.length,
    hasPlanningText: /Generating orchestration|正在生成编排|workflow_planning/i.test(text),
  };
})()"""


_GET_ASSISTANT_MESSAGE_ID_JS = """(() => {
  const debug = window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? {};
  const streamId = typeof debug.streamRequestMessageId === 'string'
    ? debug.streamRequestMessageId.trim()
    : '';
  const assistantId = window.__MYRM_E2E_CHAT__?.getLastAssistantMessageId?.() ?? null;
  return { messageId: streamId || assistantId || null };
})()"""


def wait_for_workflow_plan_card(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float | None = None,
    page_url: str | None = None,
    chat_id: str | None = None,
    stream_message_id: str | None = None,
    api_base: str | None = None,
) -> dict[str, object]:
    """Wait for Dynamic Workflow plan_confirm HITL card (spawn_count >= 1 path)."""
    resolved_timeout = timeout_sec if timeout_sec is not None else (480.0 if _parallel_chrome_e2e_active() else 420.0)
    resolved_url = page_url or get_e2e_ui_url()
    resolved_api_base = (api_base or get_e2e_api_url()).rstrip("/")
    normalized_chat_id = chat_id.strip() if isinstance(chat_id, str) else ""
    if normalized_chat_id and _dw_unattended_enabled(resolved_api_base):
        return _wait_for_yolo_dw_plan_skip(
            api_base=resolved_api_base,
            chat_id=normalized_chat_id,
            timeout_sec=resolved_timeout,
        )
    deadline = time.monotonic() + resolved_timeout
    last: dict[str, object] = {}
    blank_bridge_attempts = 0
    last_touch = 0.0
    last_api_confirm_at = 0.0
    cached_stream_id = stream_message_id.strip() if isinstance(stream_message_id, str) and stream_message_id.strip() else None

    while time.monotonic() < deadline:
        now = time.monotonic()
        if now - last_touch >= 5.0:
            touch_wall_progress(current_node="wait_for_workflow_plan_card")
            last_touch = now
        remaining = max(5.0, deadline - now)

        if now - last_api_confirm_at >= 0.25:
            last_api_confirm_at = now
            if cached_stream_id is None:
                cached_stream_id = _resolve_dw_stream_message_id(client, page)
            if normalized_chat_id:
                try:
                    payload = http_json(
                        "GET",
                        f"{resolved_api_base}/api/v1/chats/{normalized_chat_id}/messages",
                    )
                    messages = _messages_from_api_payload(payload)
                    plan_state = _plan_confirm_state_from_messages(messages)
                    if plan_state.get("phase") == "resolved":
                        touch_wall_progress(current_node="workflow_plan_api_resolved")
                        return {
                            **last,
                            "ready": True,
                            "confirmedVia": "api",
                            "planConfirmation": plan_state.get("planConfirmation"),
                        }
                    if plan_state.get("phase") == "waiting" and cached_stream_id:
                        if _post_plan_confirm_via_api(
                            resolved_api_base,
                            cached_stream_id,
                        ):
                            touch_wall_progress(current_node="workflow_plan_api_confirm")
                            return {
                                **last,
                                "ready": True,
                                "confirmedVia": "api",
                                "streamMessageId": cached_stream_id,
                            }
                except (RuntimeError, OSError, ValueError):
                    pass
            elif cached_stream_id and _post_plan_confirm_via_api(
                resolved_api_base,
                cached_stream_id,
            ):
                touch_wall_progress(current_node="workflow_plan_api_confirm")
                return {
                    **last,
                    "ready": True,
                    "confirmedVia": "api",
                    "streamMessageId": cached_stream_id,
                }

        try:
            raw = client.evaluate(
                page,
                _WORKFLOW_PLAN_CARD_JS,
                timeout_sec=min(30.0, remaining),
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            last = {"ready": False, "err": str(exc)}
            time.sleep(0.25)
            continue
        last = _coerce_evaluate_result(raw)
        if last.get("ready") is True:
            return last

        sample = str(last.get("lastAssistantSample") or "")
        if "orchestration was not approved" in sample.lower():
            raise AssertionError(f"Dynamic Workflow plan_confirm timed out before approval on {resolved_url}: {last}")

        body_len = int(last.get("bodyLength") or 0)
        stream_active = last.get("isStreaming") is True or last.get("hasPlanningText") is True
        # Never full-reload during plan wait — reload wipes kickoff stream state.
        if body_len == 0 and not stream_active and blank_bridge_attempts < 4:
            blank_bridge_attempts += 1
            touch_wall_progress(current_node="workflow_plan_blank_bridge_heal")
            try:
                wait_for_react_e2e_bridge(
                    client,
                    page,
                    timeout_sec=min(45.0, remaining),
                    page_url=resolved_url,
                )
                _ensure_orchestrator_shared_ui_session(client, page)
            except (RuntimeError, AssertionError, TimeoutError, OSError):
                pass
        elif stream_active:
            blank_bridge_attempts = 0
        time.sleep(0.25)

    raise AssertionError(
        f"Workflow plan card did not appear within {resolved_timeout}s — "
        f"check blank-page hydrate + DW orchestrator LLM on {resolved_url}: "
        f"Browser state did not become ready: {last}"
    )
