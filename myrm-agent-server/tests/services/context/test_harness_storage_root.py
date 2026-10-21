"""The harness storage root is one value shared by the run context and the idle task registry."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.agent.background_worker import registry as registry_module

from app.services.context.context_assembly import ContextAssemblyService
from app.services.skills.evolution_review.disk import enqueue_cognitive_subsumption
from app.services.skills.evolution_review.types import EvolutionApprovalPayload


def test_harness_storage_root_is_the_resolved_harness_path() -> None:
    expected = ContextAssemblyService.build_facade(ensure_layout=False).harness_path().resolve()

    assert ContextAssemblyService.harness_storage_root() == str(expected)


@pytest.mark.asyncio
async def test_subsumption_task_lands_in_the_registry_the_idle_worker_polls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry_module, "_registry_instance", None)
    monkeypatch.setattr(ContextAssemblyService, "harness_storage_root", staticmethod(lambda: str(tmp_path)))

    await enqueue_cognitive_subsumption(
        EvolutionApprovalPayload(
            skill_id="skill-1",
            skill_name="uv-usage",
            skill_path="/skills/uv-usage",
            evolution_type="fix",
            reason="user correction",
            original_content="use pip",
            evolved_content="prefer uv over pip",
            confidence=0.9,
            test_passed=True,
        )
    )

    # The harness schedules its own tasks through the same root; it must resolve to this same database.
    registry = registry_module.get_idle_task_registry(ContextAssemblyService.harness_storage_root())
    assert registry.db_path == str(tmp_path / ".context" / "system" / "idle_tasks.db")
    record = await registry.acquire_next("any-chat")
    assert record is not None
    assert record.task_type == "cognitive_subsumption"
    assert record.payload == {"new_knowledge": "prefer uv over pip", "skill_id": "skill-1"}
