"""Business-layer integration write patterns for shell command analysis.

[INPUT]
- myrm_agent_harness.toolkits.code_execution.security::register_integration_write_patterns

[OUTPUT]
- GOOGLE_WORKSPACE_INTEGRATION_WRITE_PATTERNS: regex rules for Google Workspace mutations
- register_server_integration_write_patterns(): idempotent startup registration

[POS]
Server-side shell security extensions. Keeps vendor-specific rules out of harness.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    register_integration_write_patterns,
)

GOOGLE_WORKSPACE_INTEGRATION_WRITE_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"google_api\.py\s+(gmail-send|gmail-reply|calendar-create|calendar-delete)\b",
        "Google Workspace write via skill script",
    ),
    (
        r"\bGOOGLE_WORKSPACE_TOKEN\b.*\bcurl\b.*\bgoogleapis\.com",
        "curl Google API with injected workspace token",
    ),
    (
        r"\bcurl\b.*(-X\s*POST|--request\s+POST).*\bgoogleapis\.com",
        "curl POST to Google APIs",
    ),
    (
        r"\bcurl\b.*\bgoogleapis\.com.*(-X\s*POST|--request\s+POST)",
        "curl POST to Google APIs",
    ),
    (
        r"\bcurl\b.*(-X\s*DELETE|--request\s+DELETE).*\bgoogleapis\.com",
        "curl DELETE to Google APIs",
    ),
    (
        r"\bcurl\b.*\bgoogleapis\.com.*(-X\s*DELETE|--request\s+DELETE)",
        "curl DELETE to Google APIs",
    ),
    (
        r"\bcurl\b.*(-X\s*PUT|--request\s+PUT).*\bgoogleapis\.com",
        "curl PUT to Google APIs",
    ),
)

_registered = False


def register_server_integration_write_patterns() -> None:
    """Register Myrm product integration write patterns into the harness analyzer."""
    global _registered
    if _registered:
        return
    register_integration_write_patterns(GOOGLE_WORKSPACE_INTEGRATION_WRITE_PATTERNS)
    _registered = True
