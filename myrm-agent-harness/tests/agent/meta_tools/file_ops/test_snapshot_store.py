"""Tests for the snapshot store: recording and limits, disk persistence and cleanup, message-id context variables."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
    MAX_FILE_BYTES,
    MAX_STORE_BYTES,
    FileSnapshot,
    SnapshotOp,
    SnapshotSkipReason,
    SnapshotStore,
    get_current_message_id,
    set_current_message_id,
)


@pytest.fixture(autouse=True)
def reset_store():
    """Reset singleton between tests."""
    SnapshotStore.reset()
    yield
    SnapshotStore.reset()


class TestSnapshotStore:
    def test_singleton(self):
        s1 = SnapshotStore.get()
        s2 = SnapshotStore.get()
        assert s1 is s2

    def test_reset(self):
        s1 = SnapshotStore.get()
        SnapshotStore.reset()
        s2 = SnapshotStore.get()
        assert s1 is not s2

    def test_record_and_get(self):
        store = SnapshotStore.get()
        snap = FileSnapshot(path="/a.py", operation=SnapshotOp.MODIFY, original_content="old")
        assert store.record("s1", "m1", snap)
        assert store.get_message_snapshots("s1", "m1") == [snap]

    def test_record_create_no_content(self):
        store = SnapshotStore.get()
        snap = FileSnapshot(path="/new.py", operation=SnapshotOp.CREATE, original_content=None)
        assert store.record("s1", "m1", snap)
        assert snap.size_bytes == 0

    def test_file_size_limit(self):
        store = SnapshotStore.get()
        big_content = "x" * (MAX_FILE_BYTES + 1)
        snap = FileSnapshot(path="/big.py", operation=SnapshotOp.MODIFY, original_content=big_content)
        assert not store.record("s1", "m1", snap)

    def test_record_skipped_metadata(self):
        store = SnapshotStore.get()
        store.record_skipped("s1", "m1", "/big.py", SnapshotOp.MODIFY, SnapshotSkipReason.FILE_TOO_LARGE)
        snaps = store.get_message_snapshots("s1", "m1")
        assert len(snaps) == 1
        assert snaps[0].revertible is False
        assert snaps[0].skip_reason == SnapshotSkipReason.FILE_TOO_LARGE
        assert snaps[0].size_bytes == 0
        assert store.total_bytes == 0

    def test_record_skipped_dedup(self):
        store = SnapshotStore.get()
        store.record_skipped("s1", "m1", "/big.py", SnapshotOp.MODIFY, SnapshotSkipReason.FILE_TOO_LARGE)
        store.record_skipped("s1", "m1", "/big.py", SnapshotOp.MODIFY, SnapshotSkipReason.STORE_FULL)
        assert len(store.get_message_snapshots("s1", "m1")) == 1

    def test_total_store_limit(self):
        store = SnapshotStore.get()
        chunk = "x" * (MAX_FILE_BYTES - 1)
        count = 0
        while store.total_bytes + len(chunk.encode("utf-8")) <= MAX_STORE_BYTES:
            snap = FileSnapshot(path=f"/f{count}.py", operation=SnapshotOp.MODIFY, original_content=chunk)
            if not store.record("s1", f"m{count}", snap):
                break
            count += 1
        final_snap = FileSnapshot(path="/overflow.py", operation=SnapshotOp.MODIFY, original_content=chunk)
        assert not store.record("s1", "overflow", final_snap)

    def test_get_session_snapshots(self):
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "a"))
        store.record("s1", "m2", FileSnapshot("/b.py", SnapshotOp.MODIFY, "b"))
        session = store.get_session_snapshots("s1")
        assert "m1" in session
        assert "m2" in session

    def test_get_file_snapshot(self):
        store = SnapshotStore.get()
        snap1 = FileSnapshot("/a.py", SnapshotOp.MODIFY, "v1")
        snap2 = FileSnapshot("/a.py", SnapshotOp.MODIFY, "v2")
        store.record("s1", "m1", snap1)
        store.record("s1", "m1", snap2)
        result = store.get_file_snapshot("s1", "m1", "/a.py")
        assert result is not None
        assert result.original_content == "v2"

    def test_remove_message(self):
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "old"))
        assert store.total_bytes > 0
        removed = store.remove_message("s1", "m1")
        assert len(removed) == 1
        assert store.total_bytes == 0

    def test_clear_session(self):
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "a"))
        store.record("s1", "m2", FileSnapshot("/b.py", SnapshotOp.MODIFY, "b"))
        count = store.clear_session("s1")
        assert count == 2
        assert store.total_bytes == 0

    def test_empty_queries(self):
        store = SnapshotStore.get()
        assert store.get_message_snapshots("none", "none") == []
        assert store.get_session_snapshots("none") == {}
        assert store.get_file_snapshot("none", "none", "/a") is None

    @pytest.mark.asyncio
    async def test_persist_skipped_to_disk(self):
        store = SnapshotStore.get()
        store.record_skipped("s1", "m1", "/big.py", SnapshotOp.MODIFY, SnapshotSkipReason.FILE_TOO_LARGE)

        with tempfile.TemporaryDirectory() as tmpdir:
            await store.persist_to_disk(tmpdir, "s1", "m1")
            result = await SnapshotStore.load_from_disk(tmpdir, "s1")
            assert len(result) == 1
            _, snaps = result[0]
            assert snaps[0].skip_reason == SnapshotSkipReason.FILE_TOO_LARGE
            assert snaps[0].revertible is False
            assert snaps[0].original_content is None

    @pytest.mark.asyncio
    async def test_merge_skipped_from_disk(self):
        store = SnapshotStore.get()
        store.record_skipped("s1", "m1", "/big.py", SnapshotOp.MODIFY, SnapshotSkipReason.FILE_TOO_LARGE)
        with tempfile.TemporaryDirectory() as tmpdir:
            await store.persist_to_disk(tmpdir, "s1", "m1")

            SnapshotStore.reset()
            fresh = SnapshotStore.get()
            merged = await fresh.merge_session_from_disk(tmpdir, "s1")
            assert merged is True
            snaps = fresh.get_message_snapshots("s1", "m1")
            assert len(snaps) == 1
            assert snaps[0].revertible is False

    @pytest.mark.asyncio
    async def test_persist_to_disk(self):
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "content"))

        with tempfile.TemporaryDirectory() as tmpdir:
            await store.persist_to_disk(tmpdir, "s1", "m1")
            target = Path(tmpdir) / ".myrm/snapshots/s1/m1.json"
            assert target.is_file()
            result = await SnapshotStore.load_from_disk(tmpdir, "s1")
            assert len(result) == 1
            _, snaps = result[0]
            assert snaps[0].path == "/a.py"
            assert snaps[0].original_content == "content"

    @pytest.mark.asyncio
    async def test_load_from_disk(self):
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "orig"))

        with tempfile.TemporaryDirectory() as tmpdir:
            await store.persist_to_disk(tmpdir, "s1", "m1")
            result = await SnapshotStore.load_from_disk(tmpdir, "s1")
            assert len(result) == 1
            msg_id, snaps = result[0]
            assert msg_id == "m1"
            assert snaps[0].path == "/a.py"
            assert snaps[0].original_content == "orig"

    @pytest.mark.asyncio
    async def test_merge_session_from_disk(self):
        SnapshotStore.reset()
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "orig"))
        with tempfile.TemporaryDirectory() as tmpdir:
            await store.persist_to_disk(tmpdir, "s1", "m1")

            SnapshotStore.reset()
            fresh = SnapshotStore.get()
            assert fresh.get_message_snapshots("s1", "m1") == []

            merged = await fresh.merge_session_from_disk(tmpdir, "s1")
            assert merged is True
            snaps = fresh.get_message_snapshots("s1", "m1")
            assert len(snaps) == 1
            assert snaps[0].original_content == "orig"


class TestContextVars:
    @pytest.fixture(autouse=True)
    def _isolated_message_id(self):
        """Restore the observer's message-id ContextVar so ids set here never reach later tests."""
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import _current_message_id

        token = _current_message_id.set(None)
        yield
        _current_message_id.reset(token)

    def test_set_and_get_message_id(self):
        set_current_message_id("test-msg-123")
        assert get_current_message_id() == "test-msg-123"

    def test_auto_generate_message_id(self):
        """In a fresh context, get_current_message_id generates a new msg_ ID."""
        import contextvars

        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import _current_message_id

        ctx = contextvars.copy_context()

        def _set_none_and_get():
            _current_message_id.set(None)
            return get_current_message_id()

        msg_id = ctx.run(_set_none_and_get)
        assert msg_id.startswith("msg_")

    def test_isolation_between_contexts(self):
        """Different contextvars contexts should have independent message IDs."""
        import contextvars

        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import _current_message_id

        results: list[str] = []

        def _set_and_get(val: str) -> str:
            _current_message_id.set(None)
            set_current_message_id(val)
            return get_current_message_id()

        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()
        results.append(ctx1.run(_set_and_get, "ctx1-msg"))
        results.append(ctx2.run(_set_and_get, "ctx2-msg"))
        assert results[0] == "ctx1-msg"
        assert results[1] == "ctx2-msg"


class TestDiskCleanup:
    """Tests for on-disk snapshot cleanup."""

    @pytest.mark.asyncio
    async def test_remove_persisted_message(self, tmp_path):
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "old"))
        await store.persist_to_disk(str(tmp_path), "s1", "m1")

        snap_file = tmp_path / ".myrm" / "snapshots" / "s1" / "m1.json"
        assert snap_file.is_file()

        await store.remove_persisted_message(str(tmp_path), "s1", "m1")
        assert not snap_file.exists()

    @pytest.mark.asyncio
    async def test_clear_persisted_session(self, tmp_path):
        store = SnapshotStore.get()
        store.record("s1", "m1", FileSnapshot("/a.py", SnapshotOp.MODIFY, "old"))
        store.record("s1", "m2", FileSnapshot("/b.py", SnapshotOp.CREATE, None))
        await store.persist_to_disk(str(tmp_path), "s1", "m1")
        await store.persist_to_disk(str(tmp_path), "s1", "m2")

        session_dir = tmp_path / ".myrm" / "snapshots" / "s1"
        assert session_dir.is_dir()
        assert (session_dir / "m1.json").is_file()
        assert (session_dir / "m2.json").is_file()

        await store.clear_persisted_session(str(tmp_path), "s1")
        assert not session_dir.exists()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_message_no_error(self, tmp_path):
        store = SnapshotStore.get()
        await store.remove_persisted_message(str(tmp_path), "s1", "nonexistent")

    @pytest.mark.asyncio
    async def test_clear_nonexistent_session_no_error(self, tmp_path):
        store = SnapshotStore.get()
        await store.clear_persisted_session(str(tmp_path), "nonexistent")
