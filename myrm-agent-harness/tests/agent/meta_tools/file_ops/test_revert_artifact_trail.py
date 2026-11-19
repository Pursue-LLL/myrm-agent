"""A reverted file is recorded in the artifact trail of the session it belongs to, as the file the user left.

The revert runs from an API request, not inside an agent turn, so no chat id is bound to the caller: the trail to
update is the one of the session the revert is for. A restored file still exists, so it is a modification the user
undid; only a created file that the revert removed is a deletion. The trail feeds the artifact index of a context
summary, so the group a file lands in is what the model is told about the file.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.agent.context_management.tracking.artifact_tracker import (
    ArtifactAction,
    clear_artifact_tracker,
    create_artifact_tracker,
    get_artifact_tracker,
)
from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
    FileSnapshot,
    SnapshotOp,
    SnapshotStore,
)
from myrm_agent_harness.agent.meta_tools.file_ops.revert_service import RevertService

_SESSION = "chat-revert-trail"


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    SnapshotStore.reset()
    clear_artifact_tracker(_SESSION)
    yield
    SnapshotStore.reset()
    clear_artifact_tracker(_SESSION)


def _group_of(summary: str, entry: str) -> str:
    """The group header of the artifact index that lists ``entry``."""
    group = ""
    for line in summary.splitlines():
        if line and not line.startswith(" ") and line.endswith(":"):
            group = line
        elif line == entry:
            return group
    raise AssertionError(f"{entry!r} is not in the artifact index:\n{summary}")


async def test_reverting_a_message_records_the_restored_file_as_modified_in_the_trail_of_its_session(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.py"
    path.write_text("modified", encoding="utf-8")
    create_artifact_tracker(_SESSION).record(str(path), ArtifactAction.MODIFIED, "file_edit_tool")
    SnapshotStore.get().record(_SESSION, "m1", FileSnapshot(str(path), SnapshotOp.MODIFY, "original"))

    result = await RevertService.revert_message(_SESSION, "m1")

    assert result.reverted_files == [str(path)]
    assert path.read_text(encoding="utf-8") == "original"
    tracker = get_artifact_tracker(_SESSION)
    assert tracker is not None
    latest = tracker.records[-1]
    assert (latest.path, latest.action, latest.description) == (str(path), ArtifactAction.MODIFIED, "Reverted by user")
    assert _group_of(tracker.get_summary(), f" - {path} (Reverted by user)") == "修改的文件:"


async def test_reverting_a_session_records_every_restored_file(tmp_path: Path) -> None:
    paths = [tmp_path / "a.py", tmp_path / "b.py"]
    tracker = create_artifact_tracker(_SESSION)
    for index, path in enumerate(paths):
        path.write_text("modified", encoding="utf-8")
        tracker.record(str(path), ArtifactAction.MODIFIED, "file_edit_tool")
        SnapshotStore.get().record(_SESSION, f"m{index}", FileSnapshot(str(path), SnapshotOp.MODIFY, "original"))

    await RevertService.revert_session(_SESSION)

    reverted = {record.path for record in tracker.records if record.description == "Reverted by user"}
    assert reverted == {str(path) for path in paths}
    assert not any(record.action == ArtifactAction.DELETED for record in tracker.records)


async def test_reverting_a_created_file_records_it_as_deleted(tmp_path: Path) -> None:
    path = tmp_path / "new.py"
    path.write_text("created", encoding="utf-8")
    create_artifact_tracker(_SESSION).record(str(path), ArtifactAction.CREATED, "file_write_tool")
    SnapshotStore.get().record(_SESSION, "m1", FileSnapshot(str(path), SnapshotOp.CREATE, None))

    result = await RevertService.revert_message(_SESSION, "m1")

    assert result.reverted_files == [str(path)]
    assert not path.exists()
    tracker = get_artifact_tracker(_SESSION)
    assert tracker is not None
    assert _group_of(tracker.get_summary(), f" - {path} (Reverted by user)") == "删除的文件:"


async def test_a_created_file_that_is_already_gone_is_still_recorded_as_deleted(tmp_path: Path) -> None:
    path = tmp_path / "new.py"
    create_artifact_tracker(_SESSION).record(str(path), ArtifactAction.CREATED, "file_write_tool")
    SnapshotStore.get().record(_SESSION, "m1", FileSnapshot(str(path), SnapshotOp.CREATE, None))

    await RevertService.revert_message(_SESSION, "m1")

    tracker = get_artifact_tracker(_SESSION)
    assert tracker is not None
    assert tracker.records[-1].action == ArtifactAction.DELETED


async def test_a_session_without_a_trail_gets_none_from_a_revert(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text("modified", encoding="utf-8")
    SnapshotStore.get().record(_SESSION, "m1", FileSnapshot(str(path), SnapshotOp.MODIFY, "original"))

    await RevertService.revert_message(_SESSION, "m1")

    assert get_artifact_tracker(_SESSION) is None
