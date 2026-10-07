"""Startup repair of plugin skill records that have no skill files."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage, SkillRecord

from app.database.dto import AgentUpdate
from app.services.plugins import orphan_cleanup
from app.services.plugins.orphan_cleanup import sweep_orphan_plugin_skill_records


def _record(skill_id: str, *, creator: str, path: str) -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        name=f"skill-{skill_id}",
        description="d",
        content=f"# body of {skill_id}",
        path=path,
        lineage=SkillLineage(evolution_type=EvolutionType.FIX, created_by=creator),
    )


def _ghost(skill_id: str) -> SkillRecord:
    return _record(skill_id, creator="plugin_import", path=f"plugins/demo/skill-{skill_id}/SKILL.md")


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SkillStore]:
    skill_store = SkillStore(db_path=tmp_path / "skills.db")
    yield skill_store
    skill_store.close()


@pytest.fixture
def backup_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("app.config.settings.settings.database.state_dir", str(tmp_path / "state"))
    return tmp_path / "state"


def _profile(agent_id: str, skills: list[str]) -> SimpleNamespace:
    return SimpleNamespace(id=agent_id, skills=skills)


class _Env:
    """Wires the sweep to a real store, a fake catalog and fake experts."""

    def __init__(self, store: SkillStore, installed: list[str], experts: list[SimpleNamespace]) -> None:
        self.store = store
        self.updates: list[tuple[str, list[str]]] = []
        self._installed = installed
        self._experts = experts

    async def get_agent_list(self, page: int = 1, page_size: int = 20) -> tuple[list[SimpleNamespace], int]:
        start = (page - 1) * page_size
        return self._experts[start : start + page_size], len(self._experts)

    async def update_agent(self, agent_id: str, data: AgentUpdate) -> None:
        assert data.skill_ids is not None
        self.updates.append((agent_id, list(data.skill_ids)))

    def patches(self) -> list[object]:
        return [
            patch("app.core.skills.store.evolution_store.get_evolution_skill_store", return_value=self.store),
            patch(
                "app.core.skills.store.service.skills_service.list_skills",
                AsyncMock(return_value=[SimpleNamespace(id=skill_id) for skill_id in self._installed]),
            ),
            patch("app.services.agent.agent_service.AgentService.get_agent_list", self.get_agent_list),
            patch("app.services.agent.agent_service.AgentService.update_agent", self.update_agent),
        ]


async def _sweep(env: _Env) -> orphan_cleanup.OrphanCleanupReport:
    from contextlib import ExitStack

    with ExitStack() as stack:
        for active in env.patches():
            stack.enter_context(active)  # type: ignore[arg-type]
        return await sweep_orphan_plugin_skill_records()


@pytest.mark.asyncio
async def test_dead_records_are_removed_after_a_backup_and_real_skills_are_left_alone(
    store: SkillStore, backup_dir: Path
) -> None:
    await store.save_skills_batch(
        [
            _ghost("ghost-1"),
            _ghost("ghost-2"),
            _record("evolved", creator="claude", path="skills/evolved/SKILL.md"),
            _record("hand-made", creator="human", path="plugins/mine/SKILL.md"),  # not written by an import
        ]
    )
    env = _Env(store, installed=[], experts=[])

    report = await _sweep(env)

    remaining = {record.skill_id for record in store.get_active_skills()}
    assert remaining == {"evolved", "hand-made"}
    assert report.removed_records == 2
    assert report.backup_path == backup_dir / "orphan_plugin_skill_records.jsonl"

    lines = [json.loads(line) for line in report.backup_path.read_text(encoding="utf-8").splitlines()]
    assert {line["record"]["skill_id"] for line in lines} == {"ghost-1", "ghost-2"}
    restored = SkillRecord.from_dict(lines[0]["record"])
    assert restored.content.startswith("# body of ghost-")  # the backup is complete enough to restore


@pytest.mark.asyncio
async def test_a_second_sweep_is_a_no_op(store: SkillStore, backup_dir: Path) -> None:
    await store.save_skills_batch([_ghost("ghost-1")])
    env = _Env(store, installed=[], experts=[])

    first = await _sweep(env)
    backup_before = first.backup_path.read_text(encoding="utf-8") if first.backup_path else ""
    second = await _sweep(env)

    assert first.removed_records == 1
    assert second == orphan_cleanup.OrphanCleanupReport()
    assert first.backup_path is not None and first.backup_path.read_text(encoding="utf-8") == backup_before


@pytest.mark.asyncio
async def test_a_record_that_resolves_to_an_installed_skill_is_never_removed(store: SkillStore, backup_dir: Path) -> None:
    await store.save_skills_batch([_ghost("local::abc"), _ghost("ghost-1")])
    env = _Env(store, installed=["local::abc"], experts=[_profile("expert", ["local::abc", "ghost-1"])])

    report = await _sweep(env)

    assert {record.skill_id for record in store.get_active_skills()} == {"local::abc"}
    assert report.removed_records == 1
    assert env.updates == [("expert", ["local::abc"])]  # the real binding survives


@pytest.mark.asyncio
async def test_only_dangling_bindings_are_dropped_and_untouched_experts_are_not_rewritten(
    store: SkillStore, backup_dir: Path
) -> None:
    await store.save_skills_batch([_ghost("ghost-1"), _ghost("ghost-2")])
    env = _Env(
        store,
        installed=["web-research"],
        experts=[
            _profile("a", ["web-research", "ghost-1", "other"]),
            _profile("b", ["web-research"]),
            _profile("c", []),
            _profile("d", ["ghost-1", "ghost-2"]),
        ],
    )

    report = await _sweep(env)

    assert env.updates == [("a", ["web-research", "other"]), ("d", [])]
    assert report.cleaned_bindings == 3


@pytest.mark.asyncio
async def test_every_page_of_experts_is_visited(store: SkillStore, backup_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orphan_cleanup, "_PAGE_SIZE", 2)
    await store.save_skills_batch([_ghost("ghost-1")])
    experts = [_profile(f"e{i}", ["ghost-1"]) for i in range(5)]
    env = _Env(store, installed=[], experts=experts)

    report = await _sweep(env)

    assert [agent_id for agent_id, _ in env.updates] == [f"e{i}" for i in range(5)]
    assert report.cleaned_bindings == 5


@pytest.mark.asyncio
async def test_nothing_is_deleted_when_the_catalog_cannot_be_read(store: SkillStore, backup_dir: Path) -> None:
    await store.save_skills_batch([_ghost("ghost-1")])
    env = _Env(store, installed=[], experts=[])
    patches = env.patches()
    patches[1] = patch("app.core.skills.store.service.skills_service.list_skills", AsyncMock(side_effect=RuntimeError("down")))

    from contextlib import ExitStack

    with ExitStack() as stack:
        for active in patches:
            stack.enter_context(active)  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="down"):
            await sweep_orphan_plugin_skill_records()

    assert [record.skill_id for record in store.get_active_skills()] == ["ghost-1"]
    assert not (backup_dir / "orphan_plugin_skill_records.jsonl").exists()


@pytest.mark.asyncio
async def test_a_failed_expert_update_does_not_stop_the_sweep(store: SkillStore, backup_dir: Path) -> None:
    await store.save_skills_batch([_ghost("ghost-1")])
    env = _Env(store, installed=[], experts=[_profile("bad", ["ghost-1"]), _profile("good", ["ghost-1"])])

    async def flaky_update(agent_id: str, data: AgentUpdate) -> None:
        if agent_id == "bad":
            raise ValueError("built-in experts are read-only")
        await _Env.update_agent(env, agent_id, data)

    patches = env.patches()
    patches[3] = patch("app.services.agent.agent_service.AgentService.update_agent", flaky_update)

    from contextlib import ExitStack

    with ExitStack() as stack:
        for active in patches:
            stack.enter_context(active)  # type: ignore[arg-type]
        report = await sweep_orphan_plugin_skill_records()

    assert env.updates == [("good", [])]
    assert report.removed_records == 1 and report.cleaned_bindings == 1
