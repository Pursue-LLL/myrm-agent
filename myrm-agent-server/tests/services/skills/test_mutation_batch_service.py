"""rollback_skill_mutation_batch uses write orchestrator and compensates on failure."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.skills.models import SkillType
from app.database.models import BatchSnapshot
from app.services.skills import mutation_batch_service as mbs
from app.services.skills.mutation_batch_service import (
    MutationBatchAlreadyConsumedError,
    MutationBatchCompensationError,
    MutationBatchRollbackError,
    _SkillLiveState,
    rollback_skill_mutation_batch,
)

# Stored rows always carry the time they were taken; the guard against newer batches reads it.
_CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _snapshot_row(
    *,
    skill_id: str = "skill-1",
    content: str = "before-md",
    existed_before: bool = True,
    resources: dict[str, str | None] | None = None,
) -> BatchSnapshot:
    return BatchSnapshot(
        snapshot_id="snap-1",
        batch_id="batch-1",
        skill_id=skill_id,
        skill_content_before=content,
        skill_version_before=1,
        skill_metadata={
            "batch_kind": "skill_mutation",
            "existed_before_batch": existed_before,
            "resource_files": resources or {},
        },
        created_at=_CREATED_AT,
    )


def _session_with_rows(rows: list[BatchSnapshot]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    # No other batch snapshotted these skills later; the guard against that has its own tests on real rows.
    session.scalar = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_rollback_accepts_market_replace_batch_kind() -> None:
    row = BatchSnapshot(
        snapshot_id="snap-m",
        batch_id="market-batch-1",
        skill_id="skill-1",
        skill_content_before="before-market-md",
        skill_version_before=0,
        skill_metadata={"batch_kind": "market_replace", "existed_before_batch": True, "resource_files": {}},
        created_at=_CREATED_AT,
    )
    session = _session_with_rows([row])
    live = _SkillLiveState(skill_id="skill-1", skill_md="live", resources={}, skill_existed=True)

    with (
        patch.object(mbs, "_capture_live_state", AsyncMock(return_value=live)),
        patch("app.services.skills.write_orchestrator.orchestrate_skill_file_write", AsyncMock()),
        patch("app.core.skills.config_version.bump_skill_config_version"),
    ):
        restored = await rollback_skill_mutation_batch(session, "market-batch-1")

    assert restored == 1


@pytest.mark.asyncio
async def test_rollback_restores_skill_md_via_orchestrator() -> None:
    row = _snapshot_row(resources={"scripts/foo.py": "old script"})
    session = _session_with_rows([row])
    live = _SkillLiveState(skill_id="skill-1", skill_md="live", resources={}, skill_existed=True)

    orchestrate = AsyncMock()
    with (
        patch.object(mbs, "_capture_live_state", AsyncMock(return_value=live)),
        patch("app.services.skills.write_orchestrator.orchestrate_skill_file_write", orchestrate),
        patch("app.core.skills.config_version.bump_skill_config_version"),
    ):
        restored = await rollback_skill_mutation_batch(session, "batch-1")

    assert restored == 1
    assert orchestrate.await_count == 2


@pytest.mark.asyncio
async def test_rollback_deletes_resource_when_snapshot_value_is_none() -> None:
    row = _snapshot_row(resources={"scripts/foo.py": None})
    session = _session_with_rows([row])
    live = _SkillLiveState(skill_id="skill-1", skill_md="live", resources={}, skill_existed=True)
    delete_resource = AsyncMock()

    with (
        patch.object(mbs, "_capture_live_state", AsyncMock(return_value=live)),
        patch.object(mbs, "_delete_skill_resource_file", delete_resource),
        patch("app.services.skills.write_orchestrator.orchestrate_skill_file_write", AsyncMock()),
        patch("app.core.skills.config_version.bump_skill_config_version"),
    ):
        restored = await rollback_skill_mutation_batch(session, "batch-1")

    assert restored == 1
    delete_resource.assert_awaited_once_with("skill-1", "scripts/foo.py")


@pytest.mark.asyncio
async def test_rollback_compensates_first_skill_when_second_row_fails() -> None:
    row1 = _snapshot_row(skill_id="skill-1", content="before-1")
    row2 = _snapshot_row(skill_id="skill-2", content="before-2")
    session = _session_with_rows([row1, row2])
    live1 = _SkillLiveState(skill_id="skill-1", skill_md="live-1", resources={}, skill_existed=True)
    live2 = _SkillLiveState(skill_id="skill-2", skill_md="live-2", resources={}, skill_existed=True)
    restore_live = AsyncMock()
    apply_row = AsyncMock(side_effect=[None, MutationBatchRollbackError("disk fail")])

    with (
        patch.object(
            mbs,
            "_capture_live_state",
            AsyncMock(side_effect=[live1, live2]),
        ),
        patch.object(mbs, "_apply_row_snapshot", apply_row),
        patch.object(mbs, "_restore_live_state", restore_live),
    ):
        with pytest.raises(MutationBatchRollbackError):
            await rollback_skill_mutation_batch(session, "batch-1")

    restore_live.assert_any_await(live1)


@pytest.mark.asyncio
async def test_rollback_raises_compensation_error_when_restore_live_fails() -> None:
    row1 = _snapshot_row(skill_id="skill-1", content="before-1")
    session = _session_with_rows([row1])
    live1 = _SkillLiveState(skill_id="skill-1", skill_md="live-1", resources={}, skill_existed=True)
    apply_row = AsyncMock(side_effect=MutationBatchRollbackError("disk fail"))
    restore_live = AsyncMock(side_effect=RuntimeError("comp fail"))

    with (
        patch.object(mbs, "_capture_live_state", AsyncMock(return_value=live1)),
        patch.object(mbs, "_apply_row_snapshot", apply_row),
        patch.object(mbs, "_restore_live_state", restore_live),
    ):
        with pytest.raises(MutationBatchCompensationError):
            await rollback_skill_mutation_batch(session, "batch-1")


@pytest.mark.asyncio
async def test_rollback_raises_when_snapshots_missing() -> None:
    session = _session_with_rows([])
    with pytest.raises(MutationBatchAlreadyConsumedError):
        await rollback_skill_mutation_batch(session, "batch-gone")


@pytest.mark.asyncio
async def test_rollback_deletes_batch_snapshots_after_success() -> None:
    row = _snapshot_row()
    session = _session_with_rows([row])
    live = _SkillLiveState(skill_id="skill-1", skill_md="live", resources={}, skill_existed=True)

    with (
        patch.object(mbs, "_capture_live_state", AsyncMock(return_value=live)),
        patch("app.services.skills.write_orchestrator.orchestrate_skill_file_write", AsyncMock()),
        patch("app.core.skills.config_version.bump_skill_config_version"),
    ):
        await rollback_skill_mutation_batch(session, "batch-1")

    session.execute.assert_awaited()
    delete_call = session.execute.await_args_list[-1]
    assert delete_call is not None


@pytest.mark.asyncio
async def test_rollback_deletes_skill_created_in_batch() -> None:
    row = _snapshot_row(content="", existed_before=False)
    session = _session_with_rows([row])
    live = _SkillLiveState(skill_id="skill-1", skill_md="new-md", resources={}, skill_existed=True)
    remove_created = AsyncMock(return_value=True)

    with (
        patch.object(mbs, "_capture_live_state", AsyncMock(return_value=live)),
        patch.object(mbs, "_delete_skill_created_in_batch", remove_created),
        patch("app.core.skills.config_version.bump_skill_config_version"),
    ):
        restored = await rollback_skill_mutation_batch(session, "batch-1")

    assert restored == 1
    remove_created.assert_awaited_once_with("skill-1")


@pytest.mark.asyncio
async def test_rollback_fails_closed_when_created_skill_cannot_be_removed() -> None:
    row = _snapshot_row(content="", existed_before=False)
    session = _session_with_rows([row])
    live = _SkillLiveState(skill_id="skill-1", skill_md="new-md", resources={}, skill_existed=True)

    with (
        patch.object(mbs, "_capture_live_state", AsyncMock(return_value=live)),
        patch.object(mbs, "_delete_skill_created_in_batch", AsyncMock(return_value=False)),
        patch.object(mbs, "_restore_live_state", AsyncMock()),
        pytest.raises(MutationBatchRollbackError, match="Failed to remove skill created in batch"),
    ):
        await rollback_skill_mutation_batch(session, "batch-1")


@pytest.mark.asyncio
async def test_created_local_skill_is_removed_through_the_creation_service(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    skill = SimpleNamespace(type=SkillType.LOCAL, storage_path=str(root / "demo"))
    delete_local = AsyncMock(return_value=SimpleNamespace(success=True))

    with (
        patch("app.core.skills.store.service.skills_service.get_skill", AsyncMock(return_value=skill)),
        patch("app.core.skills.creation.service.skill_creation_service.base_path", root),
        patch("app.core.skills.creation.service.skill_creation_service.delete_skill", delete_local),
    ):
        removed = await mbs._delete_skill_created_in_batch("local::abc")

    assert removed is True
    delete_local.assert_awaited_once_with("demo")


@pytest.mark.asyncio
async def test_created_local_skill_outside_the_creation_root_is_left_alone(tmp_path: Path) -> None:
    skill = SimpleNamespace(type=SkillType.LOCAL, storage_path=str(tmp_path / "elsewhere" / "demo"))
    delete_local = AsyncMock(return_value=SimpleNamespace(success=True))

    with (
        patch("app.core.skills.store.service.skills_service.get_skill", AsyncMock(return_value=skill)),
        patch("app.core.skills.creation.service.skill_creation_service.base_path", tmp_path / "skills"),
        patch("app.core.skills.creation.service.skill_creation_service.delete_skill", delete_local),
    ):
        removed = await mbs._delete_skill_created_in_batch("local::abc")

    assert removed is False
    delete_local.assert_not_awaited()


@pytest.mark.asyncio
async def test_created_skill_that_no_longer_resolves_counts_as_not_removed() -> None:
    with patch("app.core.skills.store.service.skills_service.get_skill", AsyncMock(return_value=None)):
        assert await mbs._delete_skill_created_in_batch("local::gone") is False


@pytest.mark.asyncio
async def test_created_non_local_skill_is_removed_through_the_store() -> None:
    skill = SimpleNamespace(type=SkillType.PREBUILT, storage_path="prebuilt/demo")
    delete_from_store = AsyncMock(return_value=True)

    with (
        patch("app.core.skills.store.service.skills_service.get_skill", AsyncMock(return_value=skill)),
        patch("app.core.skills.store.service.skills_service.delete_skill", delete_from_store),
    ):
        removed = await mbs._delete_skill_created_in_batch("prebuilt-1")

    assert removed is True
    delete_from_store.assert_awaited_once_with("prebuilt-1")
