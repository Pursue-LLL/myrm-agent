"""Unit tests for the SkillEvolutionEngine core API (fix/derive/capture)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.evolution.core.engine import SkillEvolutionEngine
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage, SkillRecord
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore


def _skill(name: str, *, locked: bool = False) -> SkillRecord:
    return SkillRecord(
        skill_id=name,
        name=name,
        description="Demo.",
        content="old content",
        path="",
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED),
        evolution_locked=locked,
    )


class TestSkillEvolutionEngineInit:
    """Test engine initialization and basic invariants."""

    def test_init_with_defaults(self):
        store = MagicMock(spec=SkillStore)
        engine = SkillEvolutionEngine(store)

        assert engine._store is store
        assert engine._llm is None
        assert engine._num_variants == 3

    def test_init_with_custom_params(self):
        store = MagicMock(spec=SkillStore)
        llm = MagicMock()
        engine = SkillEvolutionEngine(store, llm, num_variants_per_evolution=5)

        assert engine._llm is llm
        assert engine._num_variants == 5

    def test_init_without_event_log_backend(self):
        store = MagicMock(spec=SkillStore)
        engine = SkillEvolutionEngine(store)
        assert engine._trace_analyzer is None


class TestFixSkill:
    """Test fix_skill method."""

    @pytest.mark.asyncio
    async def test_fix_nonexistent_skill_returns_none(self):
        store = MagicMock(spec=SkillStore)
        store.get_skill.return_value = None
        engine = SkillEvolutionEngine(store)

        result = await engine.fix_skill("nonexistent", "error msg")
        assert result is None

    @pytest.mark.asyncio
    async def test_fix_locked_skill_returns_none(self):
        store = MagicMock(spec=SkillStore)
        store.get_skill.return_value = _skill("locked_skill", locked=True)
        engine = SkillEvolutionEngine(store)

        result = await engine.fix_skill("locked", "error")
        assert result is None

    @pytest.mark.asyncio
    async def test_fix_skill_no_variants_returns_none(self):
        store = MagicMock(spec=SkillStore)
        store.get_skill.return_value = _skill("test_skill")
        store.get_evolution_constraints.return_value = []

        engine = SkillEvolutionEngine(store)
        engine._variant_generator = MagicMock()
        engine._variant_generator.generate_variants = AsyncMock(return_value=[])

        result = await engine.fix_skill("test", "error")
        assert result is None


class TestDeriveSkill:
    """Test derive_skill_simple method."""

    @pytest.mark.asyncio
    async def test_derive_nonexistent_returns_none(self):
        store = MagicMock(spec=SkillStore)
        store.get_skill.return_value = None
        engine = SkillEvolutionEngine(store)

        result = await engine.derive_skill_simple("nope", "feedback")
        assert result is None

    @pytest.mark.asyncio
    async def test_derive_locked_returns_none(self):
        store = MagicMock(spec=SkillStore)
        store.get_skill.return_value = _skill("locked", locked=True)
        engine = SkillEvolutionEngine(store)

        result = await engine.derive_skill_simple("locked", "optimize")
        assert result is None


class TestDeriveSkillSimple:
    """Test derive_skill_simple method."""

    @pytest.mark.asyncio
    async def test_derive_nonexistent_skill_returns_none(self):
        store = MagicMock(spec=SkillStore)
        store.get_skill.return_value = None
        engine = SkillEvolutionEngine(store)

        result = await engine.derive_skill_simple("nonexistent", "improve it")
        assert result is None

    @pytest.mark.asyncio
    async def test_derive_calls_store(self):
        store = MagicMock(spec=SkillStore)
        store.get_skill.return_value = None
        engine = SkillEvolutionEngine(store)

        result = await engine.derive_skill_simple("missing_id", "feedback")
        assert result is None
        store.get_skill.assert_called_once_with("missing_id")
