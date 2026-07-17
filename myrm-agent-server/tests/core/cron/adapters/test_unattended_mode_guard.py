"""Guard: unattended_mode=True must be set in all background/automated agent entry points.

Background tasks (Cron, Eval, Kanban) run without human supervision.
If ask_question_tool is registered, the agent may call it and deadlock.
This test statically verifies that unattended_mode=True is present in
all known automated runner files.
"""

from __future__ import annotations

import ast
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[4]

AUTOMATED_RUNNER_FILES: dict[str, str] = {
    "app/core/cron/adapters/agent_runner.py": "Cron tasks run on schedule without user interaction",
    "app/core/eval/executor.py": "Eval runs automated benchmarks without user interaction",
    "app/services/kanban/task_runner.py": "Kanban background tasks run without user interaction",
}


def _contains_unattended_mode_true(filepath: Path) -> bool:
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            if node.arg == "unattended_mode" and isinstance(node.value, ast.Constant):
                if node.value.value is True:
                    return True
    return False


class TestUnattendedModeGuard:
    def test_all_automated_runners_set_unattended_mode(self) -> None:
        missing: list[str] = []
        for rel_path, reason in AUTOMATED_RUNNER_FILES.items():
            filepath = SERVER_ROOT / rel_path
            assert filepath.exists(), f"File not found: {rel_path}"
            if not _contains_unattended_mode_true(filepath):
                missing.append(f"{rel_path}: {reason}")

        assert not missing, "These automated runner files are missing unattended_mode=True:\n" + "\n".join(
            f"  - {m}" for m in missing
        )

    def test_unattended_general_agent_skips_ask_question_tool(self) -> None:
        """Behavioral guard: unattended_mode must prevent ask_question_tool registration."""
        from app.ai_agents.agents import AgentFactory, GeneralAgentParams
        from app.core.types import ModelConfig

        agent = AgentFactory.create_general_agent(
            GeneralAgentParams(
                query="cron task",
                model_cfg=ModelConfig(model="test/model", api_key="test-key"),
                unattended_mode=True,
                channel_name="cron",
            )
        )
        tools: list[object] = []
        agent._setup_clarification_tools(tools)
        names = {getattr(t, "name", None) for t in tools}
        assert "ask_question_tool" not in names
