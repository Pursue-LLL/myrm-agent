"""Tests for server-layer integration write pattern registration."""

from __future__ import annotations

from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    is_integration_mutation_command,
    register_integration_write_patterns,
)

from app.core.security.integration_write_patterns import (
    GOOGLE_WORKSPACE_INTEGRATION_WRITE_PATTERNS,
    register_server_integration_write_patterns,
)


def test_register_server_integration_write_patterns_idempotent() -> None:
    register_server_integration_write_patterns()
    register_server_integration_write_patterns()


def test_google_workspace_mutation_detected_after_registration() -> None:
    register_integration_write_patterns(GOOGLE_WORKSPACE_INTEGRATION_WRITE_PATTERNS)
    cmd = "python3 google_api.py gmail-send --to a@b.com"
    assert is_integration_mutation_command(cmd) is True
