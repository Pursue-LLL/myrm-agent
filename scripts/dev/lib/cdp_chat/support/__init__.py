"""Facade of the E2E chat helpers: every name that code outside this package imports.

[INPUT]
- cdp_chat.support.api_client (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.backend_log (POS: Finds the backend.log of the stack under test and reads what it recorded during a run)
- cdp_chat.support.binding (POS: Binds the chat page to the backend under test: the scripts that put the runtime identity and API base into the page, and the check that the page reports the expected one)
- cdp_chat.support.chat.clarify (POS: Clarification turns over the API: start a turn until it asks, skip the open card, and judge from stored messages whether a card is pending and the skip reached the agent)
- cdp_chat.support.chat.evidence (POS: What the stored chat messages prove about a turn: a real file-write tool call, an OK or DONE reply in the newest assistant message, the user message count)
- cdp_chat.support.chat.session (POS: Chat session calls of the E2E over the REST API: create, cancel, read messages, steer)
- cdp_chat.support.chat.stream (POS: Agent-stream turns over REST without a browser: SSE collection of a POST up to a deadline, idle time or terminal event, and the follow-up nudge turn)
- cdp_chat.support.chat.takeover (POS: Browser takeover state over the REST API: tool progress when mux probes are degraded, the ids a pending takeover resumes with, denial of stale approvals)
- cdp_chat.support.config.api_pins (POS: Pins the backend config an E2E run needs over the API: YOLO and HITL mode, onboarding complete, memory disabled, search services cleared)
- cdp_chat.support.config.page_pins (POS: Applies the same pins through the page so its config sync agrees with the backend: the PUT goes through the page, its offline queue is cleared first, and a HITL reset reloads the UI)
- cdp_chat.support.config.store (POS: Global config records over the API with optimistic locking: a per-key cross-process mutex, reads and writes with bounded retry)
- cdp_chat.support.goal (POS: Goal status of a chat over the API, the evidence the goal Chrome E2E asserts on)
- cdp_chat.support.page_js (POS: Scripts the E2E evaluates in the chat page: probes, model selection, modal dismissal, chat reset, the E2E bridge installer and the stream API binding)
- cdp_chat.support.readiness (POS: Polls until the pieces under test accept work: provider, backend, Chrome CDP and the frontend dev server)
- cdp_chat.support.timeouts (POS: Turns a base timeout into the budget a parallel run needs, from the active wave leases, parallel tests and mux peers)

[OUTPUT]
- the names in ``__all__``, re-exported from the module that defines each

[POS]
Stable import surface of the E2E chat helpers; it defines nothing itself.

A patch reaches only the readers of the module it is applied to. Code outside the package reads a name through this module at call time and sees a patch applied here; the readers inside the package hold the module that defines the name, so a test patches that module (``cdp_chat.support.chat.evidence.fetch_chat_messages``), not this one.
"""

from __future__ import annotations

from cdp_chat.support.api_client import (
    _e2e_api_get_json,
    _e2e_api_urlopen,
    get_e2e_api_url,
    get_e2e_ui_url,
    get_open_page_api_url,
    resolve_e2e_api_base,
    shared_hot_e2e_api_base,
)
from cdp_chat.support.backend_log import (
    backend_log_path,
    count_execution_cache_in_log,
    count_turn_prewarm_in_log,
    dump_backend_log_on_failure,
    print_private_backend_log_since,
    private_backend_log_offset,
    snapshot_backend_log_offset,
)
from cdp_chat.support.binding import (
    E2E_API_BINDING_PROBE_JS,
    e2e_api_base_inject_js,
    e2e_api_base_persist_source,
    e2e_page_binding_source,
    e2e_runtime_binding,
    e2e_runtime_binding_source,
    e2e_runtime_bootstrap_apply_js,
    require_e2e_api_binding_probe,
)
from cdp_chat.support.chat.clarify import (
    chat_has_pending_clarification,
    chat_messages_have_clarify_skip_done,
    chat_pending_clarification_interrupt_id,
    clarify_skip_resume_should_retry,
    is_hitl_already_resolved,
    resume_clarify_skip_via_api,
    start_clarify_turn_via_api,
)
from cdp_chat.support.chat.evidence import (
    chat_messages_have_done,
    chat_messages_have_ok,
    chat_user_message_count,
    empty_write_failure_in_messages,
    file_write_tool_call_count,
    wait_chat_messages_done,
)
from cdp_chat.support.chat.session import (
    cancel_e2e_chat_agent_via_api,
    chat_id_from_path,
    create_e2e_chat_via_api,
    fetch_chat_messages,
    steer_chat_message,
)
from cdp_chat.support.chat.stream import (
    _collect_agent_stream_events,
    nudge_agent_stream_turn,
)
from cdp_chat.support.chat.takeover import (
    chat_browser_gate_from_api,
    deny_stale_browser_takeover_approvals,
    fetch_browser_takeover_resume_ids,
)
from cdp_chat.support.config.api_pins import (
    _pin_hitl_on_api_with_retry,
    clear_search_services_ssot,
    ensure_e2e_hitl_mode,
    ensure_e2e_memory_disabled,
    ensure_e2e_onboarding_complete,
    ensure_e2e_yolo_mode,
)
from cdp_chat.support.config.page_pins import (
    ensure_e2e_hitl_mode_in_browser,
    ensure_e2e_search_cleared_in_browser,
    ensure_e2e_yolo_mode_in_browser,
    hard_reset_e2e_hitl_mode,
)
from cdp_chat.support.config.store import (
    config_write_mutex,
    fetch_config_value,
    put_config_value,
)
from cdp_chat.support.goal import (
    GOAL_PERSISTED_STATUSES,
    ensure_e2e_goal_active,
    fetch_e2e_goal_status,
    is_persisted_e2e_goal,
    post_goal_status_action,
    wait_e2e_goal_status,
)
from cdp_chat.support.page_js import (
    BRIDGE_CHAT_ID_JS,
    BRIDGE_TURN_SNAPSHOT_JS,
    DISMISS_MODALS_JS,
    E2E_BRIDGE_INSTALL_JS,
    MODEL_PROBE_JS,
    PAGE_PROBE_JS,
    PREPARE_AUTOMATION_SEND_JS,
    RESET_CHAT_JS,
    SELECT_FIRST_ENABLED_MODEL_JS,
    SELECT_MIMO_MODEL_JS,
    STREAM_API_BINDING_JS,
    WAIT_WORKSPACE_STREAM_JS,
)
from cdp_chat.support.readiness import (
    _api_provider_ready,
    fetch_provider_readiness_snapshot,
    wait_e2e_backend_ready,
    wait_e2e_cdp_ready,
    wait_e2e_provider_ready,
    warmup_frontend,
)
from cdp_chat.support.timeouts import (
    _signoff_desktop_soak_parallel_load,
    e2e_attach_timeout_ms,
    e2e_parallel_config_api_timeout_sec,
    e2e_private_api_ready_timeout_sec,
    shpoib_parallel_shell_timeout_sec,
    shpoib_shell_wait_slice_cap,
    signoff_parallel_desktop_approval_wait_sec,
    signoff_parallel_desktop_mux_step_timeout_sec,
    signoff_parallel_desktop_progress_api_wall_sec,
    signoff_parallel_desktop_turn_done_timeout_sec,
    signoff_parallel_desktop_wall_clock_fail_sec,
    signoff_parallel_force_chat_timeout_sec,
)

__all__ = [
    "BRIDGE_CHAT_ID_JS",
    "BRIDGE_TURN_SNAPSHOT_JS",
    "DISMISS_MODALS_JS",
    "E2E_API_BINDING_PROBE_JS",
    "E2E_BRIDGE_INSTALL_JS",
    "GOAL_PERSISTED_STATUSES",
    "MODEL_PROBE_JS",
    "PAGE_PROBE_JS",
    "PREPARE_AUTOMATION_SEND_JS",
    "RESET_CHAT_JS",
    "SELECT_FIRST_ENABLED_MODEL_JS",
    "SELECT_MIMO_MODEL_JS",
    "STREAM_API_BINDING_JS",
    "WAIT_WORKSPACE_STREAM_JS",
    "_api_provider_ready",
    "_collect_agent_stream_events",
    "_e2e_api_get_json",
    "_e2e_api_urlopen",
    "_pin_hitl_on_api_with_retry",
    "_signoff_desktop_soak_parallel_load",
    "backend_log_path",
    "cancel_e2e_chat_agent_via_api",
    "chat_browser_gate_from_api",
    "chat_has_pending_clarification",
    "chat_id_from_path",
    "chat_messages_have_clarify_skip_done",
    "chat_messages_have_done",
    "chat_messages_have_ok",
    "chat_pending_clarification_interrupt_id",
    "chat_user_message_count",
    "clarify_skip_resume_should_retry",
    "clear_search_services_ssot",
    "config_write_mutex",
    "count_execution_cache_in_log",
    "count_turn_prewarm_in_log",
    "create_e2e_chat_via_api",
    "deny_stale_browser_takeover_approvals",
    "dump_backend_log_on_failure",
    "e2e_api_base_inject_js",
    "e2e_api_base_persist_source",
    "e2e_attach_timeout_ms",
    "e2e_page_binding_source",
    "e2e_parallel_config_api_timeout_sec",
    "e2e_private_api_ready_timeout_sec",
    "e2e_runtime_binding",
    "e2e_runtime_binding_source",
    "e2e_runtime_bootstrap_apply_js",
    "empty_write_failure_in_messages",
    "ensure_e2e_goal_active",
    "ensure_e2e_hitl_mode",
    "ensure_e2e_hitl_mode_in_browser",
    "ensure_e2e_memory_disabled",
    "ensure_e2e_onboarding_complete",
    "ensure_e2e_search_cleared_in_browser",
    "ensure_e2e_yolo_mode",
    "ensure_e2e_yolo_mode_in_browser",
    "fetch_browser_takeover_resume_ids",
    "fetch_chat_messages",
    "fetch_config_value",
    "fetch_e2e_goal_status",
    "fetch_provider_readiness_snapshot",
    "file_write_tool_call_count",
    "get_e2e_api_url",
    "get_e2e_ui_url",
    "get_open_page_api_url",
    "hard_reset_e2e_hitl_mode",
    "is_hitl_already_resolved",
    "is_persisted_e2e_goal",
    "nudge_agent_stream_turn",
    "post_goal_status_action",
    "print_private_backend_log_since",
    "private_backend_log_offset",
    "put_config_value",
    "require_e2e_api_binding_probe",
    "resolve_e2e_api_base",
    "resume_clarify_skip_via_api",
    "shared_hot_e2e_api_base",
    "shpoib_parallel_shell_timeout_sec",
    "shpoib_shell_wait_slice_cap",
    "signoff_parallel_desktop_approval_wait_sec",
    "signoff_parallel_desktop_mux_step_timeout_sec",
    "signoff_parallel_desktop_progress_api_wall_sec",
    "signoff_parallel_desktop_turn_done_timeout_sec",
    "signoff_parallel_desktop_wall_clock_fail_sec",
    "signoff_parallel_force_chat_timeout_sec",
    "snapshot_backend_log_offset",
    "start_clarify_turn_via_api",
    "steer_chat_message",
    "wait_chat_messages_done",
    "wait_e2e_backend_ready",
    "wait_e2e_cdp_ready",
    "wait_e2e_goal_status",
    "wait_e2e_provider_ready",
    "warmup_frontend",
]
