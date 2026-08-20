"""Tests for deliverable-first prompt discipline SSOT."""

from app.ai_agents.prompts.deliverable_discipline import (
    DELIVERABLE_DISCIPLINE_RULES,
    KNOWLEDGE_WORK_IDENTITY,
    KNOWLEDGE_WORK_SYSTEM_PROMPT,
    build_knowledge_work_system_prompt,
)
from app.services.agent.builtin_specs.core import _CORE_BUILTIN_AGENTS


class TestDeliverableDisciplineSSOT:
    def test_discipline_block_contains_required_rules(self) -> None:
        rules = DELIVERABLE_DISCIPLINE_RULES
        assert "<deliverable_discipline>" in rules
        assert "kanban" in rules
        assert "use the kanban board" in rules
        assert "create or update tasks" in rules
        assert "track progress, and mark done" in rules
        assert "file tools" in rules
        assert "Do not describe file contents" in rules
        assert "heredoc" in rules
        assert "workspace/" in rules
        assert "@file_" in rules
        assert "ask one focused clarifying question" in rules

    def test_build_composes_identity_and_discipline(self) -> None:
        prompt = build_knowledge_work_system_prompt()
        assert prompt.startswith(KNOWLEDGE_WORK_IDENTITY)
        assert DELIVERABLE_DISCIPLINE_RULES.strip() in prompt

    def test_system_prompt_is_stable_constant(self) -> None:
        assert KNOWLEDGE_WORK_SYSTEM_PROMPT == build_knowledge_work_system_prompt()
        again = KNOWLEDGE_WORK_SYSTEM_PROMPT
        assert again is KNOWLEDGE_WORK_SYSTEM_PROMPT

    def test_economy_spec_uses_ssot_prompt(self) -> None:
        economy = next(spec for spec in _CORE_BUILTIN_AGENTS if spec.id == "builtin-economy")
        assert economy.system_prompt is KNOWLEDGE_WORK_SYSTEM_PROMPT
