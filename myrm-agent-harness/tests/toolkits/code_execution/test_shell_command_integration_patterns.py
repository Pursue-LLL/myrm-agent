"""Integration write patterns of the shell command analyzer (registered by the server layer)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.security import shell_command_analyzer
from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    has_escalate_threat,
    is_integration_mutation_command,
    register_integration_write_patterns,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SERVER_ROOT = _REPO_ROOT / "myrm-agent-server"


def _google_workspace_integration_write_patterns() -> tuple[tuple[str, str], ...]:
    if not _SERVER_ROOT.is_dir():
        pytest.skip("myrm-agent-server not available for Google pattern SSOT")
    server_path = str(_SERVER_ROOT)
    if server_path not in sys.path:
        sys.path.insert(0, server_path)
    from app.core.security.integration_write_patterns import GOOGLE_WORKSPACE_INTEGRATION_WRITE_PATTERNS

    return GOOGLE_WORKSPACE_INTEGRATION_WRITE_PATTERNS


@pytest.fixture(scope="module", autouse=True)
def _register_integration_write_patterns_for_tests() -> Iterator[None]:
    """Register the Google patterns for this module only; the registry is process-global."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(shell_command_analyzer, "_EXTRA_INTEGRATION_WRITE_PATTERNS", [])
        register_integration_write_patterns(_google_workspace_integration_write_patterns())
        yield


class TestIntegrationMutationDetection:
    def test_google_api_gmail_send(self) -> None:
        cmd = "python3 .claude/skills/google-workspace/scripts/google_api.py gmail-send --to a@b.com --subject Hi --body Hello"
        assert is_integration_mutation_command(cmd) is True
        threat = has_escalate_threat(cmd)
        assert threat is not None
        assert threat.category == "integration_mutation"

    def test_curl_post_googleapis(self) -> None:
        cmd = 'curl -X POST -H "Authorization: Bearer $GOOGLE_WORKSPACE_TOKEN" https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
        assert is_integration_mutation_command(cmd) is True

    def test_readonly_calendar_today_not_mutation(self) -> None:
        cmd = "python3 .claude/skills/google-workspace/scripts/google_api.py calendar-today"
        assert is_integration_mutation_command(cmd) is False


_GMAIL_SEND = (
    "python3 .claude/skills/google-workspace/scripts/google_api.py gmail-send --to a@b.com --subject Hi --body Hello"
)
_CALENDAR_TODAY = "python3 .claude/skills/google-workspace/scripts/google_api.py calendar-today"


class TestIntegrationMutationBehindWrappersAndSeparators:
    """An integration write is found in every command a line runs, however another command hands control to it."""

    @pytest.mark.parametrize(
        "template",
        [
            "echo start; {c}",
            "echo start;{c}",
            "{c};echo done",
            "{c}&&echo done",
            "ls | {c}",
            "sudo {c}",
            "env LANG=C {c}",
            "timeout 30 {c}",
            "for i in 1; do {c}; done",
            "if true; then {c}; fi",
        ],
    )
    def test_the_write_is_found(self, template: str) -> None:
        command = template.format(c=_GMAIL_SEND)

        assert is_integration_mutation_command(command) is True
        threat = has_escalate_threat(command)
        assert threat is not None
        assert threat.category == "integration_mutation"

    @pytest.mark.parametrize("quote", ["'", '"'])
    def test_the_write_is_found_in_a_script_handed_to_a_shell(self, quote: str) -> None:
        assert is_integration_mutation_command(f"bash -c {quote}{_GMAIL_SEND}{quote}") is True

    @pytest.mark.parametrize("template", ["echo start; {c}", "sudo {c}", "{c} && echo done", "bash -c '{c}'"])
    def test_a_read_only_call_is_no_mutation_whatever_wraps_it(self, template: str) -> None:
        assert is_integration_mutation_command(template.format(c=_CALENDAR_TODAY)) is False

    def test_text_that_only_mentions_the_write_is_no_mutation(self) -> None:
        assert is_integration_mutation_command(f"echo '{_GMAIL_SEND}'") is False
