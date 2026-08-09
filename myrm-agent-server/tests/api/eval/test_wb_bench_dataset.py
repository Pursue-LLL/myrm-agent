"""Unit tests for the WorkBuddy Bench dataset adapter.

Covers the four-source catalog, task → EvalCase mapping, workspace seeding
(isolation + idempotency), atomic extraction, and checksum verification.
Network access is mocked so tests run fully offline.
"""

from __future__ import annotations

import io
import shutil
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.eval import wb_bench as wb
from app.core.eval import wb_bench_workspace as wbw


def _run(coro):
    """Run an async WBBench operation synchronously (test helper)."""
    import asyncio

    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate_myrm_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point WBBench storage at a temp dir for every test."""
    monkeypatch.setattr(wb, "WB_BENCH_ROOT", tmp_path / "wb_bench")
    monkeypatch.setattr(wb, "ARCHIVES_DIR", tmp_path / "wb_bench" / "archives")
    monkeypatch.setattr(wb, "SOURCES_DIR", tmp_path / "wb_bench" / "sources")
    monkeypatch.setattr(wb, "WORKSPACES_DIR", tmp_path / "wb_bench" / "workspaces")
    # The workspace builder binds WORKSPACES_DIR by value at import time, so it
    # must be re-pointed on that module too (not just the catalog module).
    monkeypatch.setattr(wbw, "WORKSPACES_DIR", tmp_path / "wb_bench" / "workspaces")
    yield
    shutil.rmtree(tmp_path / "wb_bench", ignore_errors=True)


def _write_fake_subset(
    root: Path, subset_id: str, task_ids: list[str], *, with_tests: bool = False
) -> Path:
    """Create a fake WBBench subset layout on disk (named like a real archive)."""
    subset_dir = root / f"wb-bench-{subset_id}-v1.0"
    for task_id in task_ids:
        task_dir = subset_dir / "tasks" / task_id
        (task_dir / "environment").mkdir(parents=True)
        (task_dir / "instruction.md").write_text(f"Complete task {task_id}.")
        (task_dir / "task.toml").write_text("[verifier]\nengine = \"native\"\n")
        # A small workspace.tar.gz with one file.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            payload = f"def task_{task_id}(): pass\n".encode()
            info = tarfile.TarInfo("app.py")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        (task_dir / "environment" / "workspace.tar.gz").write_bytes(buf.getvalue())
        (task_dir / "environment" / "scorer.py").write_text("print('ok')\n")
        if with_tests:
            tests_dir = task_dir / "tests"
            tests_dir.mkdir(parents=True)
            (tests_dir / "test_app.py").write_text("def test_ok(): assert True\n")
            (tests_dir / "test.sh").write_text("#!/usr/bin/env bash\npython3 scoring.py\n")
            (tests_dir / "scoring.py").write_text(
                "import json\njson.dump({'reward': 1.0}, open('.wb_bench/reward.json', 'w'))\n"
            )
    return subset_dir


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_list_sources_reports_catalog() -> None:
    sources = wb.list_wb_bench_sources()
    assert [s["id"] for s in sources] == ["code", "web", "office", "sec"]
    assert all(s["is_downloaded"] is False for s in sources)
    assert all(s["task_count"] > 0 for s in sources)
    assert all(s["approx_size_mb"] > 0 for s in sources)


def test_unknown_subset_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown WBBench subset"):
        _run(wb.ensure_wb_bench_source("nope"))


# ---------------------------------------------------------------------------
# Download + checksum + atomic extraction
# ---------------------------------------------------------------------------


def test_download_extracts_atomically(tmp_path: Path) -> None:
    """A fresh download is checksum-verified and atomically installed."""
    subset = wb._SUBSET_BY_ID["code"]
    archive_bytes = _tar_gz_bytes("wb-bench-code-v1.0")
    expected_sha = _sha256_of(archive_bytes)

    class _FakeResp:
        headers: dict[str, str] = {}

        def __init__(self) -> None:
            self._chunks = [archive_bytes[i : i + 1024] for i in range(0, len(archive_bytes), 1024)]

        def raise_for_status(self) -> None:
            return None

        async def __aenter__(self) -> "_FakeResp":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def aiter_bytes(self, chunk_size: int):  # type: ignore[no-untyped-def]
            return _AsyncIter(self._chunks)

    class _AsyncIter:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        def __aiter__(self) -> "_AsyncIter":
            return self

        async def __anext__(self) -> bytes:
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    class _FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str) -> _FakeResp:
            assert method == "GET"
            assert url == subset.download_url
            return _FakeResp()

    with (
        patch("app.core.eval.wb_bench.httpx.Client") as mock_client,
        patch("app.core.eval.wb_bench.httpx.AsyncClient", _FakeAsyncClient),
    ):
        mock_client.return_value.__enter__.return_value.get.return_value.text = (
            f"{expected_sha}  {subset.archive}\n"
        )
        root = _run(wb.ensure_wb_bench_source("code"))

    assert (root / "tasks").is_dir()
    assert (root / "tasks" / "t1").is_dir()
    # Installed source no longer sits in a staging directory.
    assert not (wb.SOURCES_DIR / ".stage-code").exists()


def test_download_checksum_mismatch_rejected(tmp_path: Path) -> None:
    subset = wb._SUBSET_BY_ID["web"]
    archive_bytes = _tar_gz_bytes("wb-bench-web-v1.0")

    class _FakeResp:
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        async def __aenter__(self) -> "_FakeResp":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def aiter_bytes(self, chunk_size: int):  # type: ignore[no-untyped-def]
            return _AsyncIter([archive_bytes])

    class _AsyncIter:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        def __aiter__(self) -> "_AsyncIter":
            return self

        async def __anext__(self) -> bytes:
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    class _FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str) -> _FakeResp:
            return _FakeResp()

    with (
        patch(
            "app.core.eval.wb_bench.httpx.Client",
        ) as mock_client,
        patch("app.core.eval.wb_bench.httpx.AsyncClient", _FakeAsyncClient),
    ):
        # Wrong checksum in the manifest → every attempt fails verification.
        mock_client.return_value.__enter__.return_value.get.return_value.text = (
            f"{'0' * 64}  {subset.archive}\n"
        )
        with pytest.raises(ValueError, match="Failed to download"):
            _run(wb.ensure_wb_bench_source("web"))

    assert not (wb.SOURCES_DIR / "wb-bench-web-v1.0").exists()
    assert not (wb.ARCHIVES_DIR / subset.archive).exists()


def test_download_retries_transient_checksum_mismatch(tmp_path: Path) -> None:
    """A first checksum mismatch is retried and the download recovers."""
    subset = wb._SUBSET_BY_ID["web"]
    archive_bytes = _tar_gz_bytes("wb-bench-web-v1.0")
    expected_sha = _sha256_of(archive_bytes)
    attempts = {"n": 0}

    class _FakeResp:
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        async def __aenter__(self) -> "_FakeResp":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def aiter_bytes(self, chunk_size: int):  # type: ignore[no-untyped-def]
            attempts["n"] += 1
            # First response is corrupt; the retried response matches the hash.
            payload = archive_bytes if attempts["n"] > 1 else b"corrupt-" + archive_bytes
            return _AsyncIter([payload])

    class _AsyncIter:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        def __aiter__(self) -> "_AsyncIter":
            return self

        async def __anext__(self) -> bytes:
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    class _FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str) -> _FakeResp:
            return _FakeResp()

    with (
        patch("app.core.eval.wb_bench.httpx.Client") as mock_client,
        patch("app.core.eval.wb_bench.httpx.AsyncClient", _FakeAsyncClient),
    ):
        mock_client.return_value.__enter__.return_value.get.return_value.text = (
            f"{expected_sha}  {subset.archive}\n"
        )
        root = _run(wb.ensure_wb_bench_source("web"))

    assert (root / "tasks").is_dir()
    assert attempts["n"] == 2


def test_offline_reuse_installed_source(tmp_path: Path) -> None:
    """When a subset is already installed, no network is touched."""
    _write_fake_subset(wb.SOURCES_DIR, "office", ["t1", "t2"])

    with patch("app.core.eval.wb_bench.httpx") as mock_httpx:
        root = _run(wb.ensure_wb_bench_source("office"))
    assert (root / "tasks").is_dir()
    mock_httpx.assert_not_called()


def test_fetch_expected_sha256_tolerates_single_space(tmp_path: Path) -> None:
    """A single-space separated SHA256SUMS row still resolves the hash."""
    subset = wb._SUBSET_BY_ID["web"]
    expected_sha = "a" * 64
    with patch("app.core.eval.wb_bench.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value.text = (
            f"{expected_sha} {subset.archive}\n"
        )
        assert wb._fetch_expected_sha256(subset) == expected_sha


def test_ensure_installed_is_idempotent(tmp_path: Path) -> None:
    """An already-installed subset short-circuits without any download attempt."""
    _write_fake_subset(wb.SOURCES_DIR, "office", ["t1"])
    subset = wb._SUBSET_BY_ID["office"]
    wb.ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    (wb.ARCHIVES_DIR / subset.archive).write_bytes(_tar_gz_bytes("wb-bench-office-v1.0"))

    with patch.object(wb, "_download_archive") as mock_download:
        root = _run(wb.ensure_wb_bench_source("office"))

    assert (root / "tasks").is_dir()
    assert mock_download.call_count == 0


def test_build_aborts_during_workspace_preparation(tmp_path: Path) -> None:
    """should_abort is honored between task workspace preparations."""
    _write_fake_subset(wb.SOURCES_DIR, "office", ["t1", "t2"])
    subset = wb._SUBSET_BY_ID["office"]
    wb.ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    (wb.ARCHIVES_DIR / subset.archive).write_bytes(_tar_gz_bytes("wb-bench-office-v1.0"))

    prep_calls = {"n": 0}
    orig_prep = wbw._prepare_workspace

    def _counting_prep(task_dir: Path, _subset: wb.WbBenchSubset) -> Path | None:
        prep_calls["n"] += 1
        return orig_prep(task_dir, _subset)

    def _flaky_abort() -> bool:
        return prep_calls["n"] >= 1

    with (
        patch("app.core.eval.wb_bench.httpx.Client") as mock_client,
        patch.object(wbw, "_prepare_workspace", side_effect=_counting_prep),
    ):
        mock_client.return_value.__enter__.return_value.get.side_effect = OSError("offline")
        with pytest.raises(wb.DownloadAbortedError, match="aborted"):
            wb.build_wb_bench_cases("office", should_abort=_flaky_abort)

    assert prep_calls["n"] == 1


def test_safe_extract_blocks_traversal(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("../../evil.txt")
        payload = b"pwned"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))

    archive = tmp_path / "evil.tar.gz"
    archive.write_bytes(buf.getvalue())
    dest = tmp_path / "out"
    dest.mkdir()

    with pytest.raises(ValueError, match="path traversal"):
        wb._safe_extract(archive, dest)
    assert not (tmp_path / "evil.txt").exists()


# ---------------------------------------------------------------------------
# Task → EvalCase mapping + workspace seeding
# ---------------------------------------------------------------------------


def test_build_cases_maps_tasks_and_seeds_workspaces(tmp_path: Path) -> None:
    source_root = _write_fake_subset(wb.SOURCES_DIR, "sec", ["t1", "t2"], with_tests=True)
    subset = wb._SUBSET_BY_ID["sec"]

    cases: list[wbw.MultiTurnEvalCase] = []
    seed_map: dict[str, str] = {}
    for task_dir in sorted(source_root.glob("tasks/*")):
        workspace = wbw._prepare_workspace(task_dir, subset)
        case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
        cases.append(case)
        seed_map[case.turns[0].message] = str(workspace)

    assert len(cases) == 2
    assert len(cases) == len(seed_map)
    for case, message in zip(cases, seed_map.keys(), strict=True):
        ws_path = seed_map[message]
        assert case.turns[0].message == message
        assert case.metadata["wb_bench_source"] == "sec"
        assert case.metadata["wb_bench_task_id"] in {"t1", "t2"}
        # Security tasks grade natively via their own scorer; the adapter
        # injects a test_suite rule assertion backed by the mirrored tests.
        assert case.metadata["wb_bench_scoring"] == "native"
        assertion = case.turns[0].sandbox_assertions
        assert len(assertion) == 1
        assert assertion[0].type == "test_suite"
        assert ".wb_bench/tests" in assertion[0].target
        assert (Path(ws_path) / "app.py").exists()
        assert (Path(ws_path) / ".wb_bench" / "tests" / "test.sh").exists()


def test_workspace_seed_is_isolated_and_idempotent(tmp_path: Path) -> None:
    """Seeded workspaces live in the WBBench cache and are reusable across runs."""
    source_root = _write_fake_subset(wb.SOURCES_DIR, "sec", ["t1"])
    task_dir = next(source_root.glob("tasks/*"))
    subset = wb._SUBSET_BY_ID["sec"]

    ws1 = wbw._prepare_workspace(task_dir, subset)
    ws2 = wbw._prepare_workspace(task_dir, subset)
    assert ws1 == ws2
    assert (ws1 / "app.py").read_text().startswith("def task_t1")
    # Cache marker guarantees the extraction ran exactly once semantically.
    assert (ws1.parent / ".ready").is_file()


def test_workspace_archive_top_level_dir_unwrapped(tmp_path: Path) -> None:
    """A workspace archive bundling a single top-level dir is unwrapped."""
    task_dir = tmp_path / "t5"
    (task_dir / "environment").mkdir(parents=True)
    (task_dir / "instruction.md").write_text("task")
    (task_dir / "task.toml").write_text('[verifier]\nengine = "composite"\n')

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        payload = b"print('hi')\n"
        info = tarfile.TarInfo("workspace/main.py")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        readme = b"# task\n"
        info2 = tarfile.TarInfo("workspace/README.md")
        info2.size = len(readme)
        tar.addfile(info2, io.BytesIO(readme))
    (task_dir / "environment" / "workspace.tar.gz").write_bytes(buf.getvalue())

    ws = wbw._prepare_workspace(task_dir, wb._SUBSET_BY_ID["code"])
    assert ws is not None
    assert (ws / "main.py").is_file()
    assert (ws / "README.md").is_file()
    assert not (ws / "workspace").exists()


def test_workspace_archive_preserves_symlinks(tmp_path: Path) -> None:
    """Symlinked files inside a workspace archive survive extraction."""
    task_dir = tmp_path / "t6"
    (task_dir / "environment").mkdir(parents=True)
    (task_dir / "instruction.md").write_text("task")
    (task_dir / "task.toml").write_text('[verifier]\nengine = "composite"\n')

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        payload = b"real\n"
        info = tarfile.TarInfo("src/real.py")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        link = tarfile.TarInfo("src/alias.py")
        link.type = tarfile.SYMTYPE
        link.linkname = "real.py"
        tar.addfile(link)
    (task_dir / "environment" / "workspace.tar.gz").write_bytes(buf.getvalue())

    ws = wbw._prepare_workspace(task_dir, wb._SUBSET_BY_ID["code"])
    assert ws is not None
    alias = ws / "alias.py"
    assert alias.is_symlink()
    assert alias.resolve() == (ws / "real.py").resolve()


def test_scoring_mode_recorded_in_metadata(tmp_path: Path) -> None:
    """Each task is tagged with its grading mode."""
    task_dir = tmp_path / "t3"
    (task_dir / "environment").mkdir(parents=True)
    (task_dir / "instruction.md").write_text("no scorer task")
    (task_dir / "task.toml").write_text("[verifier]\nengine = \"composite\"\n")
    subset = wb._SUBSET_BY_ID["code"]

    # Without a workspace / mirrored tests, no rule assertion is injected.
    case = wbw._case_for_task(task_dir, subset, workspace_dir=None)
    assert case.turns[0].sandbox_assertions == []
    assert case.metadata["wb_bench_scoring"] == "composite"

    sec_case = wbw._case_for_task(task_dir, wb._SUBSET_BY_ID["sec"], workspace_dir=None)
    assert sec_case.metadata["wb_bench_scoring"] == "native"


def test_code_and_web_assertion_injection(tmp_path: Path) -> None:
    """Code tasks carry a pytest rule assertion; Web tasks stay assertion-free."""
    source_root = _write_fake_subset(wb.SOURCES_DIR, "code", ["t1"], with_tests=True)
    subset = wb._SUBSET_BY_ID["code"]
    task_dir = next(source_root.glob("tasks/*"))

    workspace = wbw._prepare_workspace(task_dir, subset)
    assert workspace is not None
    assert (workspace / ".wb_bench" / "tests" / "test_app.py").exists()

    code_case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assertion = code_case.turns[0].sandbox_assertions
    assert len(assertion) == 1
    assert assertion[0].type == "test_suite"
    assert "pytest" in assertion[0].target
    assert assertion[0].result_file == ".wb_bench/results.xml"

    web_case = wbw._case_for_task(task_dir, wb._SUBSET_BY_ID["web"], workspace_dir=workspace)
    assert web_case.turns[0].sandbox_assertions == []
    assert web_case.metadata["wb_bench_scoring"] == "composite"


def test_no_tests_no_assertion(tmp_path: Path) -> None:
    """A workspace without a tests dir yields no rule assertion."""
    source_root = _write_fake_subset(wb.SOURCES_DIR, "office", ["t1"])
    subset = wb._SUBSET_BY_ID["office"]
    task_dir = next(source_root.glob("tasks/*"))

    workspace = wbw._prepare_workspace(task_dir, subset)
    assert workspace is not None
    assert not (workspace / ".wb_bench" / "tests").exists()

    case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assert case.turns[0].sandbox_assertions == []


def test_no_workspace_archive_returns_none(tmp_path: Path) -> None:
    task_dir = tmp_path / "t4"
    task_dir.mkdir()
    assert wbw._prepare_workspace(task_dir, wb._SUBSET_BY_ID["code"]) is None


def test_full_build_requires_real_subset(tmp_path: Path) -> None:
    """build_wb_bench_cases without a local download raises (network is mocked off)."""
    with (
        patch("app.core.eval.wb_bench.httpx.Client") as mock_client,
        patch("app.core.eval.wb_bench.httpx.AsyncClient") as mock_async,
    ):
        mock_client.return_value.__enter__.return_value.get.side_effect = OSError("offline")
        mock_async.side_effect = OSError("offline")
        with pytest.raises((OSError, ValueError)):
            wb.build_wb_bench_cases("code")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tar_gz_bytes(top_dir: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for task_id in ("t1", "t2"):
            content = f"# {task_id}\n".encode()
            info = tarfile.TarInfo(f"{top_dir}/tasks/{task_id}/instruction.md")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _sha256_of(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
