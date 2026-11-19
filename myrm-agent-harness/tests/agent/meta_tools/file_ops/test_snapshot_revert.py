"""Tests for the snapshot observer and the revert service."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
    MAX_FILE_BYTES,
    FileSnapshot,
    SnapshotObserver,
    SnapshotOp,
    SnapshotSkipReason,
    SnapshotStore,
    set_current_message_id,
)
from myrm_agent_harness.agent.meta_tools.file_ops.revert_service import RevertService
from tests.support.windows_text_mode import emulate_windows_text_mode

_REVERTED_TEXTS = {
    "lf": "alpha\nbeta\n",
    "crlf": "alpha\r\nbeta\r\n",
    "mixed": "alpha\r\nbeta\ngamma\r\n",
    "unicode_crlf": "héllo\r\n世界\r\n",
}


@pytest.fixture(autouse=True)
def reset_store() -> Iterator[None]:
    """Reset singleton between tests."""
    SnapshotStore.reset()
    yield
    SnapshotStore.reset()


class TestSnapshotObserver:
    @pytest.mark.asyncio
    async def test_on_file_created(self) -> None:
        observer = SnapshotObserver()
        set_current_message_id("test-create")

        with patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer._get_session_id",
            return_value="test-session",
        ):
            await observer.on_file_created("/new.py", "content")

        store = SnapshotStore.get()
        snaps = store.get_message_snapshots("test-session", "test-create")
        assert len(snaps) == 1
        assert snaps[0].operation == SnapshotOp.CREATE
        assert snaps[0].original_content is None

    @pytest.mark.asyncio
    async def test_on_file_modified(self) -> None:
        observer = SnapshotObserver()
        set_current_message_id("test-modify")

        with patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer._get_session_id",
            return_value="test-session",
        ):
            await observer.on_file_modified("/a.py", "old-content", "new-content")

        store = SnapshotStore.get()
        snaps = store.get_message_snapshots("test-session", "test-modify")
        assert len(snaps) == 1
        assert snaps[0].operation == SnapshotOp.MODIFY
        assert snaps[0].original_content == "old-content"

    @pytest.mark.asyncio
    async def test_on_file_modified_skips_large_file(self) -> None:
        observer = SnapshotObserver()
        set_current_message_id("test-large")

        big = "x" * (MAX_FILE_BYTES + 1)
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer._get_session_id",
            return_value="test-session",
        ):
            await observer.on_file_modified("/big.py", big, big + "y")

        store = SnapshotStore.get()
        snaps = store.get_message_snapshots("test-session", "test-large")
        assert len(snaps) == 1
        assert snaps[0].skip_reason == SnapshotSkipReason.FILE_TOO_LARGE

    @pytest.mark.asyncio
    async def test_on_file_viewed_noop(self) -> None:
        observer = SnapshotObserver()
        await observer.on_file_viewed("/a.py")
        store = SnapshotStore.get()
        assert store.total_bytes == 0


class TestRevertService:
    @pytest.mark.asyncio
    async def test_revert_modify(self) -> None:
        store = SnapshotStore.get()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("modified-content")
            f.flush()
            path = f.name

        try:
            store.record("s1", "m1", FileSnapshot(path, SnapshotOp.MODIFY, "original-content"))
            result = await RevertService.revert_message("s1", "m1")
            assert path in result.reverted_files
            assert Path(path).read_text("utf-8") == "original-content"
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.asyncio
    async def test_revert_create(self) -> None:
        store = SnapshotStore.get()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("new file")
            f.flush()
            path = f.name

        store.record("s1", "m1", FileSnapshot(path, SnapshotOp.CREATE, None))
        result = await RevertService.revert_message("s1", "m1")
        assert path in result.reverted_files
        assert not os.path.exists(path)

    @pytest.mark.asyncio
    async def test_revert_no_snapshots(self) -> None:
        result = await RevertService.revert_message("none", "none")
        assert result.reverted_files == []
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_revert_file_not_found(self) -> None:
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/nonexistent.py", SnapshotOp.MODIFY, "old"))
        result = await RevertService.revert_message("s1", "m1")
        assert "/nonexistent.py" in result.skipped_files

    @pytest.mark.asyncio
    async def test_revert_already_matches(self) -> None:
        store = SnapshotStore.get()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("original")
            path = f.name

        try:
            store.record("s1", "m1", FileSnapshot(path, SnapshotOp.MODIFY, "original"))
            result = await RevertService.revert_message("s1", "m1")
            assert path in result.reverted_files
        finally:
            os.remove(path)

    @pytest.mark.asyncio
    async def test_revert_non_utf8_content_skips(self) -> None:
        store = SnapshotStore.get()
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\xff\xfe\x00\x01binary-bytes")
            path = f.name

        try:
            store.record("s1", "m1", FileSnapshot(path, SnapshotOp.MODIFY, "original-text"))
            result = await RevertService.revert_message("s1", "m1")
            assert path in result.skipped_files
            assert len(result.warnings) > 0
            assert Path(path).read_bytes().startswith(b"\xff\xfe")
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.asyncio
    async def test_get_message_changes_skipped(self) -> None:
        store = SnapshotStore.get()
        store.record_skipped("s1", "m1", "/big.py", SnapshotOp.MODIFY, SnapshotSkipReason.FILE_TOO_LARGE)
        changes = await RevertService.get_message_changes("s1", "m1")
        assert len(changes) == 1
        assert changes[0].revertible is False
        assert changes[0].skip_reason == "file_too_large"

    @pytest.mark.asyncio
    async def test_revert_message_only_skipped(self) -> None:
        store = SnapshotStore.get()
        store.record_skipped("s1", "m1", "/big.py", SnapshotOp.MODIFY, SnapshotSkipReason.FILE_TOO_LARGE)
        result = await RevertService.revert_message("s1", "m1")
        assert result.reverted_files == []
        assert "/big.py" in result.skipped_files

    @pytest.mark.asyncio
    async def test_revert_message_mixed_includes_non_revertible_in_skipped(self) -> None:
        store = SnapshotStore.get()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("v2")
            small_path = f.name
        try:
            store.record("s1", "m1", FileSnapshot(small_path, SnapshotOp.MODIFY, "v1"))
            store.record_skipped("s1", "m1", "/big.py", SnapshotOp.MODIFY, SnapshotSkipReason.FILE_TOO_LARGE)
            result = await RevertService.revert_message("s1", "m1")
            assert small_path in result.reverted_files
            assert "/big.py" in result.skipped_files
        finally:
            Path(small_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_message_changes(self) -> None:
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "old"))
        store.record("s1", "m1", FileSnapshot("/b.py", SnapshotOp.CREATE, None))
        changes = await RevertService.get_message_changes("s1", "m1")
        assert len(changes) == 2
        assert changes[0].path == "/a.py"
        assert changes[0].has_original is True
        assert changes[1].path == "/b.py"
        assert changes[1].has_original is False

    @pytest.mark.asyncio
    async def test_dedup_same_file(self) -> None:
        """Multiple edits to same file: revert should use first snapshot's content."""
        store = SnapshotStore.get()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("v3")
            path = f.name

        try:
            store.record("s1", "m1", FileSnapshot(path, SnapshotOp.MODIFY, "v1"))
            store.record("s1", "m1", FileSnapshot(path, SnapshotOp.MODIFY, "v2"))
            await RevertService.revert_message("s1", "m1")
            assert Path(path).read_text("utf-8") == "v2"
        finally:
            if os.path.exists(path):
                os.remove(path)

    @pytest.mark.asyncio
    async def test_revert_session(self) -> None:
        """Revert all changes in a session."""
        store = SnapshotStore.get()
        paths: list[str] = []

        for i in range(2):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(f"modified-{i}")
                paths.append(f.name)
            store.record("s1", f"m{i}", FileSnapshot(paths[-1], SnapshotOp.MODIFY, f"original-{i}"))

        try:
            result = await RevertService.revert_session("s1")
            assert len(result.reverted_files) == 2
            for i, path in enumerate(paths):
                assert Path(path).read_text("utf-8") == f"original-{i}"
        finally:
            for p in paths:
                if os.path.exists(p):
                    os.remove(p)

    @pytest.mark.asyncio
    async def test_get_session_changes(self) -> None:
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "old"))
        store.record("s1", "m2", FileSnapshot("/b.py", SnapshotOp.CREATE, None))
        changes = await RevertService.get_session_changes("s1")
        assert "m1" in changes
        assert "m2" in changes
        assert len(changes["m1"]) == 1
        assert len(changes["m2"]) == 1

    @pytest.mark.asyncio
    async def test_revert_create_with_container_path(self) -> None:
        """Container-abstract snapshot paths (/workspace/...) must map to the real file."""
        from myrm_agent_harness.core.context_vars import workspace_root_var

        store = SnapshotStore.get()
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "created_e2e.txt"
            local_path.write_text("content", encoding="utf-8")
            workspace_root_var.set(tmpdir)

            store.record("s1", "m1", FileSnapshot("/workspace/created_e2e.txt", SnapshotOp.CREATE, None))
            result = await RevertService.revert_message("s1", "m1")
            assert not local_path.exists()
            assert "/workspace/created_e2e.txt" in result.reverted_files
        workspace_root_var.set("")

    @pytest.mark.asyncio
    async def test_revert_modify_with_container_path(self) -> None:
        from myrm_agent_harness.core.context_vars import workspace_root_var

        store = SnapshotStore.get()
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "batch_edit_e2e.txt"
            local_path.write_text("modified", encoding="utf-8")
            workspace_root_var.set(tmpdir)

            store.record("s1", "m1", FileSnapshot("/workspace/batch_edit_e2e.txt", SnapshotOp.MODIFY, "original"))
            result = await RevertService.revert_message("s1", "m1")
            assert local_path.read_text("utf-8") == "original"
            assert "/workspace/batch_edit_e2e.txt" in result.reverted_files
        workspace_root_var.set("")

    @pytest.mark.asyncio
    async def test_revert_plain_absolute_path_unchanged(self) -> None:
        """Non-container absolute paths must still revert without workspace binding."""
        store = SnapshotStore.get()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("modified")
            path = f.name
        try:
            store.record("s1", "m1", FileSnapshot(path, SnapshotOp.MODIFY, "original"))
            result = await RevertService.revert_message("s1", "m1")
            assert path in result.reverted_files
            assert Path(path).read_text("utf-8") == "original"
        finally:
            os.remove(path)

    @pytest.mark.asyncio
    async def test_revert_modify_no_original(self) -> None:
        """MODIFY snapshot with None original_content should be skipped."""
        store = SnapshotStore.get()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("current")
            path = f.name

        try:
            store.record("s1", "m1", FileSnapshot(path, SnapshotOp.MODIFY, None))
            result = await RevertService.revert_message("s1", "m1")
            assert path in result.skipped_files
        finally:
            os.remove(path)


class TestRevertKeepsLineEndings:
    """A reverted file holds the snapshot's text byte-for-byte, also where text mode translates newlines (Windows)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("current", [b"modified\r\n", None], ids=["differs", "already_original"])
    @pytest.mark.parametrize("original", _REVERTED_TEXTS.values(), ids=_REVERTED_TEXTS.keys())
    async def test_file_holds_the_snapshot_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, original: str, current: bytes | None
    ) -> None:
        path = tmp_path / "f.txt"
        path.write_bytes(original.encode("utf-8") if current is None else current)
        SnapshotStore.get().record("s1", "m1", FileSnapshot(str(path), SnapshotOp.MODIFY, original))
        emulate_windows_text_mode(monkeypatch)

        result = await RevertService.revert_message("s1", "m1")

        assert str(path) in result.reverted_files
        assert path.read_bytes() == original.encode("utf-8")
