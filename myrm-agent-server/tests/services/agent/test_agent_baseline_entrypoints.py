"""Guard: every non-fast agent entry point must force AGENT_BASELINE_BUILTIN_TOOLS."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[3]

_ENTRYPOINTS: tuple[tuple[str, str], ...] = (
    ("app/services/agent/params/converter.py", "apply_agent_baseline_tool_flags"),
    ("app/core/channel_bridge/agent_executor/executor.py", "apply_agent_baseline_tool_flags"),
    ("app/core/cron/adapters/agent_runner.py", "apply_agent_baseline_tool_flags"),
    ("app/services/kanban/task_runner.py", "apply_agent_baseline_tool_flags"),
    ("app/api/voice/agent_bridge.py", "apply_agent_baseline_tool_flags"),
    ("app/core/eval/executor.py", "apply_agent_baseline_tool_flags"),
)


@pytest.mark.parametrize(("relative_path", "required_symbol"), _ENTRYPOINTS)
def test_agent_entrypoint_applies_baseline_tool_flags(
    relative_path: str,
    required_symbol: str,
) -> None:
    source = (_SERVER_ROOT / relative_path).read_text(encoding="utf-8")
    assert required_symbol in source, (
        f"{relative_path} must call {required_symbol} for non-fast agent runs"
    )
