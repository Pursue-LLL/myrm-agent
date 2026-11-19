"""Chat-page actions of the clarify Skip live E2E: prepare a fresh chat, hand the UI stream over to the API.

[INPUT]
- cdp_chat.mcp_ui::McpChatSession (POS: Chat UI session backed by the Chrome DevTools MCP mux owner model)
- dev_gate.contract::EvaluateIntent (POS: Dev Gate contract SSOT for Chrome MCP E2E orchestration: error tokens, parallel caps and timeout budgets)
- tests.api.agent.utils (POS: Agent test helpers: lite model selection and provider-prefix handling)
- tests.e2e.clarify_skip.bridge_js (POS: page-side scripts of the clarify Skip E2E)
- tests.e2e.clarify_skip.constants (POS: page origin, prompts and wait budget of the clarify Skip E2E)

[OUTPUT]
- release_ui_stream_for_api(chat): drop the WebUI SSE lease (no cancel API) so the API can resume the paused run
- prepare_fresh_clarify_chat(chat): dismiss modals, open a new chat, enable structured clarify and pin the lite model

[POS]
Chat-page setup and stream hand-over steps shared by the wait, resume and flow modules.
"""

from __future__ import annotations

from cdp_chat.mcp_ui import McpChatSession
from dev_gate.contract import EvaluateIntent

from tests.api.agent.utils import _strip_provider_prefix, get_lite_model_selection
from tests.e2e.clarify_skip.bridge_js import (
    DISMISS_MIGRATION_JS,
    ENABLE_STRUCTURED_CLARIFY_JS,
    PIN_LITE_MODEL_JS,
    RELEASE_UI_STREAM_FOR_API_JS,
)
from tests.e2e.clarify_skip.constants import BASE_URL


async def release_ui_stream_for_api(chat: McpChatSession) -> dict[str, object]:
    released = await chat.evaluate(
        RELEASE_UI_STREAM_FOR_API_JS,
        intent=EvaluateIntent.SYNC_PROBE,
    )
    assert isinstance(released, dict), f"releaseActiveStreamForApiResume: {released}"
    return released


async def _enable_structured_clarify(chat: McpChatSession) -> None:
    await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
    enabled = await chat.evaluate(ENABLE_STRUCTURED_CLARIFY_JS, intent=EvaluateIntent.SYNC_PROBE)
    assert isinstance(enabled, dict)
    assert enabled.get("ok") is True, f"Failed to enable structured_clarify: {enabled}"
    pinned = await chat.evaluate(PIN_LITE_MODEL_JS, intent=EvaluateIntent.AGENT_SUBMIT)
    assert isinstance(pinned, dict)
    assert pinned.get("ok") is True, f"Failed to pin lite model for clarify E2E: {pinned}"
    expected_lite = get_lite_model_selection()
    pinned_model = pinned.get("pinned")
    assert isinstance(pinned_model, dict), f"Missing pinned model payload: {pinned}"
    assert pinned_model.get("providerId") == expected_lite["providerId"], (
        f"Pinned provider mismatch: {pinned_model} vs {expected_lite}"
    )
    assert pinned_model.get("model") == _strip_provider_prefix(str(expected_lite["model"])), (
        f"Pinned model mismatch: {pinned_model} vs {expected_lite}"
    )


async def prepare_fresh_clarify_chat(chat: McpChatSession) -> None:
    await chat.evaluate(DISMISS_MIGRATION_JS, intent=EvaluateIntent.SYNC_PROBE)
    await chat.dismiss_modals()
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    await _enable_structured_clarify(chat)
