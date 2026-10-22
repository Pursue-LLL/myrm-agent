"""Guardrail: production GeneralAgentParams entry points must apply profile output suffixes.

GeneralAgentParams constructor allowlist is guarded separately by
``tests/core/agents/test_general_agent_params_callsites_guard.py``.

Ten paths (Web, Channel, Cron, Kanban, Eval, Voice×3, Subagent, Goal stream).
"""

from __future__ import annotations

from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[4]

PROFILE_OUTPUT_SUFFIX_REQUIRED: frozenset[str] = frozenset(
    {
        "app/services/agent/params/converter.py",
        "app/core/channel_bridge/agent_executor/execute_preamble/instructions.py",
        "app/core/cron/adapters/agent_runner.py",
        "app/services/kanban/task_runner/runner.py",
        "app/core/eval/executor.py",
        "app/api/voice/agent_bridge.py",
        "app/api/voice/realtime.py",
        "app/api/voice/gemini_live.py",
        "app/ai_agents/custom_agent_factory.py",
        "app/services/agent/goals/goal_stream_trigger.py",
    }
)


def test_profile_output_suffix_applied_at_entry_points() -> None:
    missing: list[str] = []
    for rel in sorted(PROFILE_OUTPUT_SUFFIX_REQUIRED):
        text = (SERVER_ROOT / rel).read_text(encoding="utf-8")
        if "apply_profile_output_suffixes" not in text:
            missing.append(rel)
    assert not missing, (
        "Entry points missing apply_profile_output_suffixes:\n"
        + "\n".join(f"  - {rel}" for rel in missing)
        + "\nWire profile_output_suffixes or update PROFILE_OUTPUT_SUFFIX_REQUIRED."
    )


def test_web_converter_forwards_resolved_personality_style() -> None:
    """Web 主对话路径必须把解析出的风格传进后缀注入（而不是丢弃风格）。"""
    text = (SERVER_ROOT / "app/services/agent/params/converter.py").read_text(encoding="utf-8")
    assert "personality_style=resolved.personality_style" in text, (
        "converter.py 必须把 resolved.personality_style 传给 apply_profile_output_suffixes"
    )


def test_personality_block_text_has_single_source() -> None:
    """注入文本只能在 personality_templates.render_personality_block 拼装一次。

    子 Agent 工厂与 Web/渠道等入口都必须复用该渲染器，禁止各写一份
    「**Communication Style**:」拼接，否则作用域不变量会分叉。
    """
    for rel in (
        "app/services/agent/params/profile_output_suffixes.py",
        "app/ai_agents/custom_agent_factory.py",
    ):
        text = (SERVER_ROOT / rel).read_text(encoding="utf-8")
        assert "render_personality_block" in text, f"{rel} 必须复用 render_personality_block"
        assert "**Communication Style**" not in text, f"{rel} 不得自行拼接风格块文本"
