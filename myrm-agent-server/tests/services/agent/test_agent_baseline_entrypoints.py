"""Guard: every non-fast agent entry point must call resolve_agent_mount.

Dual-track SSOT: harness tool_layers.py (CORE registry) + tool_mount.resolve_agent_mount.
See app/services/agent/_ARCH.md §Tool loading dual-track and tool_mount/_ARCH.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[3]

_ENTRYPOINTS: tuple[tuple[str, str, str], ...] = (
    ("app/services/agent/params/converter.py", "resolve_agent_mount", "ExecutionSurface.WEB_CHAT"),
    ("app/core/channel_bridge/agent_executor/execute_preamble_agent.py", "resolve_agent_mount", "ExecutionSurface.CHANNEL"),
    ("app/core/cron/adapters/tools_policy.py", "resolve_agent_mount", "ExecutionSurface.CRON"),
    ("app/services/kanban/task_runner.py", "resolve_agent_mount", "ExecutionSurface.KANBAN"),
    ("app/api/voice/agent_bridge.py", "resolve_agent_mount", "ExecutionSurface.VOICE"),
    ("app/api/voice/voice_memory_context.py", "resolve_agent_mount", "ExecutionSurface.VOICE"),
    ("app/core/eval/executor.py", "resolve_agent_mount", "ExecutionSurface.EVAL"),
)


@pytest.mark.parametrize(("relative_path", "required_symbol", "required_surface"), _ENTRYPOINTS)
def test_agent_entrypoint_uses_mount_resolver(
    relative_path: str,
    required_symbol: str,
    required_surface: str,
) -> None:
    source = (_SERVER_ROOT / relative_path).read_text(encoding="utf-8")
    assert required_symbol in source, (
        f"{relative_path} must call {required_symbol} for non-fast agent runs"
    )
    assert required_surface in source, (
        f"{relative_path} must pass {required_surface} to resolve_agent_mount"
    )
