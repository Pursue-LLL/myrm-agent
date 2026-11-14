"""Shared real-Chrome MCP helpers for formal UI E2E tests.

Submodules, primitives first: each imports only modules listed before it, except ``reload``, which reaches
``wait_state`` at call time because ``wait_for_state`` heals through ``reload_mcp_page``.

- ``parallel_load``: How busy the shared Chrome stack is: parallel-session detection and the waits that scale with it.
- ``api``: Effect-guarded HTTP access to the E2E backend and the identity of the backend process.
- ``probe_result``: Read what an in-page probe returned: result coercion and the blank-page and transport-error
  classifications.
- ``warm_ui``: Warm the shared UI before a page opens: route warm-up plus the attach-time frontend heal and client
  warm-up.
- ``reload``: Reload or navigate a page and re-bind the isolated private runtime that a reload wipes.
- ``page_guard``: Keep an E2E page usable: desktop viewport, offscreen window restore, blocking modals, chrome-error
  pages and a settings page stuck on its loading shell.
- ``bridge_diagnostics``: What the React E2E bridge wait reports about a page that has not hydrated.
- ``bridge``: Wait for the React E2E bridge to appear on a page, healing a stuck load without reloading a slow one.
- ``wait_state``: Poll an in-page predicate until it reports ready, healing blank, errored or modal-covered pages on
  the way.
- ``private_api``: Bind the active page to the isolated private API and wait until that API is healthy.
- ``settings_wait``: Wait for the settings shell, the agent settings editor and the wiki settings shell; settings URL
  helpers.
- ``open_page_mux``: Mux-facing guards of opening a page: the scoped attach restart and the CDP readiness probe.
- ``open_page``: Open a page through the browser orchestrator: open_mcp_page, its async form and the shared-UI
  session.
- ``settings_open``: Open a settings sub-route, or the wiki settings page, on a page that is ready for it.
- ``chat``: Chat page helpers: route readiness, agent binding, the security preset trigger and the send-idle wait.
- ``plan_api``: Dynamic-workflow plan and stream state read and confirmed through the HTTP API.
- ``workflow_plan``: Wait for the workflow plan card and confirm the plan in the UI or through the API.
- ``patching``: Monkeypatch helper for the per-concern layout of this package.

The package re-exports what the E2E tests import; ``__all__`` is that contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The dev libraries (cdp_chat, chrome_mcp, dev_gate, e2e_core) live outside the test roots; every submodule imports them.
_DEV_LIB = Path(__file__).resolve().parents[4] / "scripts/dev/lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from cdp_chat.support import (
    e2e_runtime_binding,
    e2e_runtime_bootstrap_apply_js,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_provider_ready,
)
from chrome_mcp.client import ChromeMcpClient, McpPage

from .api import get_first_enabled_model, guarded_httpx_request, guarded_urlopen, http_json, prepare_e2e_ui_session
from .bridge import wait_for_react_e2e_bridge
from .chat import attach_chat_and_wait_agent_binding, ensure_chat_route, wait_for_chat_send_idle, wait_for_security_preset_trigger
from .open_page import OpenMcpPageSession, open_mcp_page, open_mcp_page_async
from .open_page_mux import _force_mux_attach_restart_after_new_page_timeout, _require_e2e_cdp_ready
from .page_guard import _restore_e2e_window_via_cdp, dismiss_blocking_modals, ensure_desktop_viewport
from .parallel_load import _parallel_chrome_e2e_active, _parallel_open_page_peer_count, _warm_ui_parallel_wait_sec
from .plan_api import _resolve_dw_stream_message_id, wait_for_dw_stream_done_via_api
from .private_api import _ensure_e2e_private_api_live
from .probe_result import _coerce_evaluate_result
from .reload import _reapply_shpoib_runtime_after_reload, navigate_mcp_page, reload_mcp_page
from .settings_open import open_settings_subroute, open_wiki_settings_mcp_page
from .settings_wait import wait_for_agent_settings_editor, wait_for_settings_layout, wait_for_wiki_settings_shell
from .wait_state import wait_for_state
from .warm_ui import _trigger_attach_client_warmup_once, warm_ui_route
from .workflow_plan import wait_for_workflow_plan_card

__all__ = [
    "ChromeMcpClient",
    "McpPage",
    "OpenMcpPageSession",
    "_coerce_evaluate_result",
    "_ensure_e2e_private_api_live",
    "_force_mux_attach_restart_after_new_page_timeout",
    "_parallel_chrome_e2e_active",
    "_parallel_open_page_peer_count",
    "_reapply_shpoib_runtime_after_reload",
    "_require_e2e_cdp_ready",
    "_resolve_dw_stream_message_id",
    "_restore_e2e_window_via_cdp",
    "_trigger_attach_client_warmup_once",
    "_warm_ui_parallel_wait_sec",
    "attach_chat_and_wait_agent_binding",
    "dismiss_blocking_modals",
    "e2e_runtime_binding",
    "e2e_runtime_bootstrap_apply_js",
    "ensure_chat_route",
    "ensure_desktop_viewport",
    "get_e2e_api_url",
    "get_e2e_ui_url",
    "get_first_enabled_model",
    "guarded_httpx_request",
    "guarded_urlopen",
    "http_json",
    "navigate_mcp_page",
    "open_mcp_page",
    "open_mcp_page_async",
    "open_settings_subroute",
    "open_wiki_settings_mcp_page",
    "prepare_e2e_ui_session",
    "reload_mcp_page",
    "wait_e2e_provider_ready",
    "wait_for_agent_settings_editor",
    "wait_for_chat_send_idle",
    "wait_for_dw_stream_done_via_api",
    "wait_for_react_e2e_bridge",
    "wait_for_security_preset_trigger",
    "wait_for_settings_layout",
    "wait_for_state",
    "wait_for_wiki_settings_shell",
    "wait_for_workflow_plan_card",
    "warm_ui_route",
]
