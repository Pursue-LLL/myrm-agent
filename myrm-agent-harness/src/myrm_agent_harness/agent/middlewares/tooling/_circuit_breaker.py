"""Hard circuit breaker over the run's terminal errors.

[INPUT]
- agent.errors.tool_error_category::ToolErrorCategory (POS: Canonical tool error categories for structured error classification.)
- agent.middlewares._session_context::get_terminal_errors (POS: Middleware session context; the run's registry of errors no retry can fix)
- agent.middlewares.tooling._tool_helpers::make_error_msg (POS: Stateless helper functions)

[OUTPUT]
- check_circuit_breaker(): the blocking tool result for a call whose resource family has hit a terminal error, else None

[POS]
Pre-call guard of the tool interceptor. Once a terminal error (no network, read-only sandbox, broken search or
browser configuration) is registered, calls to the tools that depend on that resource are refused with a hint
instead of being retried; a broken configuration blocks only its own family.
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.errors.tool_error_category import ToolErrorCategory
from myrm_agent_harness.agent.middlewares._session_context import get_terminal_errors
from myrm_agent_harness.agent.middlewares.tooling._tool_helpers import make_error_msg
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)


def check_circuit_breaker(tool_name: str, tool_call_id: str) -> ToolMessage | None:
    """The error result that blocks ``tool_name``, or ``None`` when no registered terminal error covers it."""
    registry = get_terminal_errors()
    terminal_errors = registry.get_all()
    if not terminal_errors:
        return None

    t_lower = tool_name.lower()
    is_network_tool = any(kw in t_lower for kw in ["web", "search", "browser", "fetch", "http", "network", "mcp"])
    is_write_tool = any(kw in t_lower for kw in ["write", "edit", "create", "delete", "mkdir", "rm", "append"])

    blocker = None
    if "any" in terminal_errors:
        blocker = "any"
    elif "network_blocked" in terminal_errors and is_network_tool:
        blocker = "network_blocked"
    elif "sandbox_ro" in terminal_errors and is_write_tool:
        blocker = "sandbox_ro"
    elif config_auth_families := {
        category.split(":", 1)[1] for category in terminal_errors if category.startswith("config_or_auth:")
    }:
        # Family-scoped: a broken search configuration must not disable
        # browser tools (independent infrastructure) and vice versa.
        tool_family = "search" if "search" in t_lower else ("browser" if "browser" in t_lower else None)
        if tool_family in config_auth_families:
            blocker = f"config_or_auth:{tool_family}"

    if blocker:
        if blocker.startswith("config_or_auth:"):
            family = blocker.split(":", 1)[1]
            detail = (
                "The related service is unavailable because its configuration "
                "or credentials are invalid. This cannot be fixed by retrying."
            )
            if family == "search":
                detail = (
                    "Search is unavailable because the search service configuration "
                    "or credentials are invalid. Use browser or web_fetch tools instead."
                )
            elif family == "browser":
                detail = (
                    "Browser tools are unavailable because the browser environment "
                    "failed to launch. Use search or web_fetch tools instead."
                )
            hint = f"Circuit breaker active for {family} tools. {detail}"
        else:
            hint = f"Circuit breaker active for {blocker}. Previous failures indicate this resource is unavailable."
        logger.warning("Circuit breaker: blocked %s due to terminal %s", tool_name, blocker)
        return make_error_msg(
            tool_name,
            tool_call_id,
            f"Error: [SYSTEM_ENFORCED] Execution of '{tool_name}' blocked by circuit breaker.\nDetails: {hint}",
            error_category=ToolErrorCategory.CIRCUIT_BREAKER,
            error_hint=hint,
        )
    return None
