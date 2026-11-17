"""Integration test: verify ANSI is stripped from real persistent session SSE output.

This test uses a real LocalPersistentSession (no mocks on the critical path)
to execute a command that explicitly outputs ANSI escape codes, then verifies
the SSE dispatched data is clean.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
    SessionConfig,
)
from tests.toolkits.code_execution._session_helpers import captured_stdout_chunks


def _make_config() -> SessionConfig:
    return SessionConfig(
        session_id="integration-ansi-test",
        work_dir="/tmp",
        timeout=10,
        sandbox_mode="disable",
    )


class TestAnsiSanitizationIntegration:
    """Full-pipeline integration: real shell → real StreamOutputProcessor → verified clean SSE."""

    @pytest.mark.asyncio
    async def test_ansi_stripped_from_sse_dispatch(self) -> None:
        """Execute a command that outputs raw ANSI, capture SSE events, verify clean."""
        session = LocalPersistentSession(_make_config())
        await session.start()

        try:
            with captured_stdout_chunks() as captured_chunks:
                # printf outputs raw ANSI without checking isatty
                result = await session.execute(r"printf '\033[31mRED_TEXT\033[0m normal_text\n'")

            assert result.success, f"Command failed: {result.error}"

            full_sse_output = "".join(captured_chunks)
            assert "\x1b" not in full_sse_output, f"ANSI ESC byte leaked to SSE: {full_sse_output!r}"
            assert "[31m" not in full_sse_output, f"ANSI CSI fragment visible in SSE: {full_sse_output!r}"
            assert "RED_TEXT" in full_sse_output
            assert "normal_text" in full_sse_output
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_no_color_env_suppresses_color_tools(self) -> None:
        """Verify that NO_COLOR=1 is set in the shell environment."""
        session = LocalPersistentSession(_make_config())
        await session.start()
        try:
            result = await session.execute("echo $NO_COLOR")
            assert result.success
            assert "1" in result.stdout.strip()

            result = await session.execute("echo $TERM")
            assert result.success
            assert "dumb" in result.stdout.strip()
        finally:
            await session.close()
