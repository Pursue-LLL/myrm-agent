"""Unit tests for the shared eval concurrency + dataset storage helpers.

Covers ``app.core.eval.adaptive`` (chat-activity yielding manager) and
``app.core.eval.datasets`` (JSONL dataset persistence), which are shared by
the single-profile, matrix, and memory A/B eval flows.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.eval.adaptive import (
    AdaptiveEvalManager,
    _last_chat_activity_time,
    mark_chat_activity,
)
from app.core.eval.datasets import (
    _dataset_sort_key,
    get_all_datasets,
    get_dataset_path,
    get_eval_cases,
    save_eval_cases,
)


class TestMarkChatActivity:
    def test_mark_chat_activity_updates_timestamp(self) -> None:
        old = _last_chat_activity_time
        mark_chat_activity()
        assert _last_chat_activity_time >= old


class TestAdaptiveEvalManager:
    @pytest.mark.asyncio
    async def test_no_chat_activity_acquires_quickly(self) -> None:
        global _last_chat_activity_time
        _last_chat_activity_time = 0.0
        manager = AdaptiveEvalManager(max_concurrency=1, idle_wait_seconds=0.0)
        async with manager:
            assert manager._semaphore.locked() is True

    @pytest.mark.asyncio
    async def test_active_chat_waits_until_idle_window(self) -> None:
        global _last_chat_activity_time
        import time

        _last_chat_activity_time = time.time()
        manager = AdaptiveEvalManager(max_concurrency=1, idle_wait_seconds=0.2)
        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            async with manager:
                assert manager._semaphore.locked() is True
        # The yielding loop must have slept at least once.
        mock_sleep.assert_awaited()

    @pytest.mark.asyncio
    async def test_semaphore_released_on_exit(self) -> None:
        _last_chat_activity_time = 0.0
        manager = AdaptiveEvalManager(max_concurrency=1, idle_wait_seconds=0.0)
        async with manager:
            assert manager._semaphore.locked() is True
        assert manager._semaphore.locked() is False

    @pytest.mark.asyncio
    async def test_max_concurrency_respected(self) -> None:
        _last_chat_activity_time = 0.0
        manager = AdaptiveEvalManager(max_concurrency=2, idle_wait_seconds=0.0)
        assert manager._semaphore._value == 2


class TestDatasetSortKey:
    def test_numeric_timestamp(self) -> None:
        assert _dataset_sort_key({"updated_at": 100.0}) == 100.0
        assert _dataset_sort_key({"updated_at": 5}) == 5.0

    def test_missing_or_non_numeric_falls_back(self) -> None:
        assert _dataset_sort_key({}) == 0.0
        assert _dataset_sort_key({"updated_at": "n/a"}) == 0.0


class TestGetDatasetPath:
    def test_creates_root(self, tmp_path: Path) -> None:
        root = tmp_path / "eval_datasets"
        with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", root):
            path = get_dataset_path("custom-1")
        assert root.exists()
        assert path == root / "custom-1.jsonl"

    def test_sanitizes_dataset_id(self, tmp_path: Path) -> None:
        with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", tmp_path):
            path = get_dataset_path("../evil name!")
        assert path.name == "evilname.jsonl"
        assert ".." not in str(path)

    def test_default_migrates_legacy_file(self, tmp_path: Path) -> None:
        root = tmp_path / "eval_datasets"
        legacy = Path(".myrm/eval_cases.jsonl")
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("{}")
        try:
            with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", root):
                path = get_dataset_path("default")
            assert (root / "default.jsonl").exists()
            assert not legacy.exists()
            assert path == root / "default.jsonl"
        finally:
            legacy.unlink(missing_ok=True)
            (legacy.parent / "default.jsonl").unlink(missing_ok=True)


class TestGetAllDatasets:
    def test_returns_empty_when_none(self, tmp_path: Path) -> None:
        root = tmp_path / "datasets"
        with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", root):
            datasets = get_all_datasets()
        assert datasets == []

    def test_sorted_newest_first(self, tmp_path: Path) -> None:
        root = tmp_path / "datasets"
        root.mkdir()
        (root / "a.jsonl").write_text("x")
        (root / "b.jsonl").write_text("y")
        import os
        import time

        older = time.time() - 100
        os.utime(root / "a.jsonl", (older, older))
        with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", root):
            datasets = get_all_datasets()
        assert [d["id"] for d in datasets] == ["b", "a"]
        assert datasets[0]["filename"] == "b.jsonl"
        assert "size" in datasets[0]


class TestEvalCasesReadWrite:
    def test_get_missing_returns_empty(self, tmp_path: Path) -> None:
        root = tmp_path / "datasets"
        with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", root):
            assert get_eval_cases("nope") == ""

    def test_roundtrip_save_and_read(self, tmp_path: Path) -> None:
        root = tmp_path / "datasets"
        with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", root):
            assert save_eval_cases('{"a":1}', "my-ds") is True
            assert get_eval_cases("my-ds") == '{"a":1}'

    def test_save_to_unwritable_path_returns_false(self, tmp_path: Path) -> None:
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        readonly.chmod(0o400)
        with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", readonly):
            assert save_eval_cases("data", "x") is False

    def test_read_error_returns_empty(self, tmp_path: Path) -> None:
        root = tmp_path / "datasets"
        root.mkdir()
        target = root / "bad.jsonl"
        target.write_text("{}")
        with (
            patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", root),
            patch("pathlib.Path.open", side_effect=OSError("locked")),
        ):
            assert get_eval_cases("bad") == ""

    def test_default_dataset_id_uses_default_file(self, tmp_path: Path) -> None:
        root = tmp_path / "datasets"
        with patch("app.core.eval.datasets.DEFAULT_DATASETS_DIR", root):
            assert get_dataset_path(None) == root / "default.jsonl"
            assert get_dataset_path("default") == root / "default.jsonl"
