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

from app.core.eval.wb_bench import download as wb
from app.core.eval.wb_bench import workspace as wbw


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
    root: Path,
    subset_id: str,
    task_ids: list[str],
    *,
    verifier_family: str | None = None,
    office_grading: bool = False,
    direct_scorer: str | None = None,
) -> Path:
    """Create a fake WBBench subset layout on disk (named like a real archive).

    ``verifier_family`` drives which native grading assets are shipped under
    ``tests/`` (matching the official ``verifier.toml`` protocol): one of
    ``script_verifier`` / ``pytest_injected`` / ``repo_understanding``, or None
    to ship no grading assets at all. ``office_grading`` ships an Office-style
    verifier.toml (no ``family``, ``[run] command`` + ``[env]``), and
    ``direct_scorer`` ships ``tests/scoring.py`` / ``tests/test_outputs.py``
    writing ``reward.json`` directly (Security track).
    """
    subset_dir = root / f"wb-bench-{subset_id}-v1.0"
    for task_id in task_ids:
        task_dir = subset_dir / "tasks" / task_id
        (task_dir / "environment").mkdir(parents=True)
        (task_dir / "instruction.md").write_text(f"Complete task {task_id}.")
        (task_dir / "task.toml").write_text('[verifier]\nengine = "native"\n')
        # Reference solution stays outside the agent workspace.
        (task_dir / "gold.patch").write_text("diff --git a/app.py b/app.py\n")
        # A small workspace.tar.gz with one file.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            payload = f"def task_{task_id}(): pass\n".encode()
            info = tarfile.TarInfo("app.py")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        (task_dir / "environment" / "workspace.tar.gz").write_bytes(buf.getvalue())
        (task_dir / "environment" / "scorer.py").write_text("print('ok')\n")
        if verifier_family is not None:
            tests_dir = task_dir / "tests"
            tests_dir.mkdir(parents=True)
            if verifier_family == "script_verifier":
                (tests_dir / "verifier.toml").write_text('family = "script_verifier"\n')
                (tests_dir / "verifier.py").write_text(
                    "import os\n"
                    "from pathlib import Path\n"
                    "log_dir = Path(os.environ['LOG_DIR'])\n"
                    "log_dir.mkdir(parents=True, exist_ok=True)\n"
                    "reward = 1.0 if Path(os.environ['WORKSPACE'], 'app.py').exists() else 0.0\n"
                    "(log_dir / 'reward.txt').write_text(str(reward))\n"
                )
            elif verifier_family == "pytest_injected":
                (tests_dir / "verifier.toml").write_text(
                    'family = "pytest_injected"\n'
                    "[run]\n"
                    'command = "python -m pytest --junitxml=/logs/verifier/results.xml"\n'
                )
                injected = tests_dir / "injected" / "tests"
                injected.mkdir(parents=True)
                (injected / "test_app.py").write_text("def test_ok(): assert True\n")
            elif verifier_family == "repo_understanding":
                (tests_dir / "verifier.toml").write_text(
                    'family = "repo_understanding"\n'
                )
                (tests_dir / "scorer.py").write_text(
                    "import json\n"
                    "json.dump({'reward': 1.0}, open('.wb_bench/reward.json', 'w'))\n"
                )
            else:
                raise AssertionError(f"unknown verifier_family={verifier_family}")
        if office_grading:
            tests_dir = task_dir / "tests"
            (tests_dir / "grading").mkdir(parents=True)
            (tests_dir / "gold").mkdir(parents=True)
            (tests_dir / "grading" / "test_verify.py").write_text(
                "def test_grading(): assert True\n"
            )
            (tests_dir / "gold" / "gold_answer.json").write_text("{}")
            (tests_dir / "verifier.toml").write_text(
                'schema_version = "workbuddy.office.verifier.v1"\n'
                "\n"
                "[run]\n"
                'cwd = "/workspace"\n'
                'command = """PYTHONPATH=\\"/workspace:${PYTHONPATH:-}\\" python3 -m pytest /tests/grading \\\\\n'
                "    -p no:cacheprovider -v --tb=short \\\\\n"
                "    --junitxml=/logs/verifier/results.xml \\\\\n"
                '    > /logs/verifier/test_output.txt 2>&1"""\n'
                "\n"
                "[env]\n"
                'WB_BENCH_FIXTURES_DIR = "/tests/gold/fixtures"\n'
                'WB_BENCH_GOLD_PATH = "/tests/gold/gold_answer.json"\n'
            )
        if direct_scorer is not None:
            assert direct_scorer in ("scoring.py", "test_outputs.py")
            tests_dir = task_dir / "tests"
            tests_dir.mkdir(parents=True)
            (tests_dir / direct_scorer).write_text(
                "import json\n"
                "from pathlib import Path\n"
                "from os import environ\n"
                "ws = Path(environ['WORKSPACE'])\n"
                "reward = 1.0 if (ws / 'app.py').exists() else 0.0\n"
                "Path(ws, 'reward.json').write_text(json.dumps({'reward': reward}))\n"
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
            self._chunks = [
                archive_bytes[i : i + 1024] for i in range(0, len(archive_bytes), 1024)
            ]

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
        patch("app.core.eval.wb_bench.download.httpx.Client") as mock_client,
        patch("app.core.eval.wb_bench.download.httpx.AsyncClient", _FakeAsyncClient),
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
            "app.core.eval.wb_bench.download.httpx.Client",
        ) as mock_client,
        patch("app.core.eval.wb_bench.download.httpx.AsyncClient", _FakeAsyncClient),
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
            payload = (
                archive_bytes if attempts["n"] > 1 else b"corrupt-" + archive_bytes
            )
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
        patch("app.core.eval.wb_bench.download.httpx.Client") as mock_client,
        patch("app.core.eval.wb_bench.download.httpx.AsyncClient", _FakeAsyncClient),
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

    with patch("app.core.eval.wb_bench.download.httpx") as mock_httpx:
        root = _run(wb.ensure_wb_bench_source("office"))
    assert (root / "tasks").is_dir()
    mock_httpx.assert_not_called()


def test_fetch_expected_sha256_tolerates_single_space(tmp_path: Path) -> None:
    """A single-space separated SHA256SUMS row still resolves the hash."""
    subset = wb._SUBSET_BY_ID["web"]
    expected_sha = "a" * 64
    with patch("app.core.eval.wb_bench.download.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value.text = (
            f"{expected_sha} {subset.archive}\n"
        )
        assert wb._fetch_expected_sha256(subset) == expected_sha


def test_ensure_installed_is_idempotent(tmp_path: Path) -> None:
    """An already-installed subset short-circuits without any download attempt."""
    _write_fake_subset(wb.SOURCES_DIR, "office", ["t1"])
    subset = wb._SUBSET_BY_ID["office"]
    wb.ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    (wb.ARCHIVES_DIR / subset.archive).write_bytes(
        _tar_gz_bytes("wb-bench-office-v1.0")
    )

    with patch.object(wb, "_download_archive") as mock_download:
        root = _run(wb.ensure_wb_bench_source("office"))

    assert (root / "tasks").is_dir()
    assert mock_download.call_count == 0


def test_build_aborts_during_workspace_preparation(tmp_path: Path) -> None:
    """should_abort is honored between task workspace preparations."""
    _write_fake_subset(wb.SOURCES_DIR, "office", ["t1", "t2"])
    subset = wb._SUBSET_BY_ID["office"]
    wb.ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    (wb.ARCHIVES_DIR / subset.archive).write_bytes(
        _tar_gz_bytes("wb-bench-office-v1.0")
    )

    prep_calls = {"n": 0}
    orig_prep = wbw._prepare_workspace

    def _counting_prep(task_dir: Path, _subset: wb.WbBenchSubset) -> Path | None:
        prep_calls["n"] += 1
        return orig_prep(task_dir, _subset)

    def _flaky_abort() -> bool:
        return prep_calls["n"] >= 1

    with (
        patch("app.core.eval.wb_bench.download.httpx.Client") as mock_client,
        patch.object(wbw, "_prepare_workspace", side_effect=_counting_prep),
    ):
        mock_client.return_value.__enter__.return_value.get.side_effect = OSError(
            "offline"
        )
        with pytest.raises(wb.DownloadAbortedError, match="aborted"):
            wbw.build_wb_bench_cases("office", should_abort=_flaky_abort)

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
    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "sec", ["t1", "t2"], verifier_family="script_verifier"
    )
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
        assert case.metadata["wb_bench_scoring"] == "native"
        assertion = case.turns[0].sandbox_assertions
        assert len(assertion) == 1
        assert assertion[0].type == "test_suite"
        # script_verifier wiring: WORKSPACE/LOG_DIR env vars drive verifier.py
        # from the read-only source cache; nothing is mirrored into the agent
        # workspace (no gold.patch exposure).
        assert "WORKSPACE={workspace}" in assertion[0].target
        assert "verifier.py" in assertion[0].target
        assert assertion[0].result_file == "{workspace}/.wb_bench/logs/reward.txt"
        assert len(assertion[0].readonly_paths) == 1
        ws = Path(ws_path)
        assert (ws / "app.py").exists()
        assert not (ws / ".wb_bench" / "tests").exists()
        assert not (ws / "gold.patch").exists()
        # Read-only grading assets point at the source cache, not the workspace.
        assert Path(assertion[0].readonly_paths[0]).is_dir()


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
    (task_dir / "task.toml").write_text('[verifier]\nengine = "composite"\n')
    subset = wb._SUBSET_BY_ID["code"]

    # Without a workspace / mirrored tests, no rule assertion is injected.
    case = wbw._case_for_task(task_dir, subset, workspace_dir=None)
    assert case.turns[0].sandbox_assertions == []
    assert case.metadata["wb_bench_scoring"] == "composite"

    sec_case = wbw._case_for_task(task_dir, wb._SUBSET_BY_ID["sec"], workspace_dir=None)
    assert sec_case.metadata["wb_bench_scoring"] == "native"


def test_code_and_web_assertion_injection(tmp_path: Path) -> None:
    """Code tasks carry a pytest-injected rule assertion; Web tasks stay assertion-free."""
    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "code", ["t1"], verifier_family="pytest_injected"
    )
    subset = wb._SUBSET_BY_ID["code"]
    task_dir = next(source_root.glob("tasks/*"))

    workspace = wbw._prepare_workspace(task_dir, subset)
    assert workspace is not None
    # Injected tests stay in the source cache; the agent workspace only has
    # the task skeleton (no .wb_bench/tests, no gold.patch).
    assert not (workspace / ".wb_bench" / "tests").exists()
    assert not (workspace / "gold.patch").exists()

    code_case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assertion = code_case.turns[0].sandbox_assertions
    assert len(assertion) == 1
    assert assertion[0].type == "test_suite"
    assert "python -m pytest" in assertion[0].target
    assert "cp -r" in assertion[0].target
    assert assertion[0].result_file == "{workspace}/.wb_bench/results.xml"
    assert assertion[0].readonly_paths == (str(task_dir / "tests"),)

    web_case = wbw._case_for_task(
        task_dir, wb._SUBSET_BY_ID["web"], workspace_dir=workspace
    )
    assert web_case.turns[0].sandbox_assertions == []
    assert web_case.metadata["wb_bench_scoring"] == "composite"


def test_repo_understanding_assertion_injection(tmp_path: Path) -> None:
    """repo_understanding tasks wire scorer.py against the seeded repo."""
    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "code", ["t1"], verifier_family="repo_understanding"
    )
    subset = wb._SUBSET_BY_ID["code"]
    task_dir = next(source_root.glob("tasks/*"))

    workspace = wbw._prepare_workspace(task_dir, subset)
    case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assertion = case.turns[0].sandbox_assertions
    assert len(assertion) == 1
    assert assertion[0].type == "test_suite"
    assert "scorer.py" in assertion[0].target
    assert "--repo {workspace}" in assertion[0].target
    assert assertion[0].result_file == "{workspace}/.wb_bench/reward.json"
    assert assertion[0].readonly_paths == (str(task_dir / "tests"),)


def test_pytest_injected_command_rewrites_harbor_log_path(tmp_path: Path) -> None:
    """Harbor log dirs in the declared pytest command map to the live workspace."""
    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "code", ["t1"], verifier_family="pytest_injected"
    )
    task_dir = next(source_root.glob("tasks/*"))
    subset = wb._SUBSET_BY_ID["code"]

    case = wbw._case_for_task(task_dir, subset, workspace_dir=task_dir)
    target = case.turns[0].sandbox_assertions[0].target
    assert "{workspace}/.wb_bench/results.xml" in target
    assert "/logs/verifier/" not in target


def test_pytest_injected_keeps_declared_command_variants(tmp_path: Path) -> None:
    """The whole declared command runs, incl. option flags and custom runners.

    Real Code tasks declare ``python -W ignore::... -m pytest`` (flags between
    interpreter and pytest) and ``bash -lc 'cd tests && python3 runtests.py ...'``
    (a non-pytest runner). Both must survive command building verbatim.
    """
    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "code", ["t1", "t2"], verifier_family="pytest_injected"
    )
    (source_root / "tasks" / "t1" / "tests" / "verifier.toml").write_text(
        'family = "pytest_injected"\n'
        "[run]\n"
        'command = "python -W ignore::PendingDeprecationWarning -m pytest -q --junitxml=/logs/verifier/results.xml"\n'
    )
    (source_root / "tasks" / "t2" / "tests" / "verifier.toml").write_text(
        'family = "pytest_injected"\n'
        "[run]\n"
        "command = \"bash -lc 'cd tests && python3 runtests.py --settings=test_sqlite -v 2'\"\n"
    )
    subset = wb._SUBSET_BY_ID["code"]

    for task_id, expected in (
        ("t1", "python -W ignore::PendingDeprecationWarning -m pytest -q"),
        ("t2", "python3 runtests.py --settings=test_sqlite"),
    ):
        task_dir = source_root / "tasks" / task_id
        case = wbw._case_for_task(task_dir, subset, workspace_dir=task_dir)
        target = case.turns[0].sandbox_assertions[0].target
        assert expected in target
        assert "{workspace}/.wb_bench/results.xml" in target or "runtests.py" in target


def test_missing_verifier_toml_yields_no_assertion(tmp_path: Path) -> None:
    """Tasks without verifier.toml fall back to composite/VLM grading."""
    source_root = _write_fake_subset(wb.SOURCES_DIR, "code", ["t1"])
    task_dir = next(source_root.glob("tasks/*"))
    subset = wb._SUBSET_BY_ID["code"]

    case = wbw._case_for_task(task_dir, subset, workspace_dir=task_dir)
    assert case.turns[0].sandbox_assertions == []
    assert case.metadata["wb_bench_scoring"] == "composite"


def test_office_verifier_injects_pytest_grading(tmp_path: Path) -> None:
    """Office tasks with a verifier.toml get a pytest grading assertion.

    Office verifier.toml has no ``family`` key; it declares ``[run] command``
    (pytest against /tests/grading) plus ``[env]`` paths. The generated command
    rewrites Harbor mounts to the read-only source cache and the live workspace.
    """
    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "office", ["t1"], office_grading=True
    )
    subset = wb._SUBSET_BY_ID["office"]
    task_dir = next(source_root.glob("tasks/*"))

    workspace = wbw._prepare_workspace(task_dir, subset)
    assert workspace is not None
    case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assertion = case.turns[0].sandbox_assertions
    assert len(assertion) == 1
    assert assertion[0].type == "test_suite"
    assert "pytest" in assertion[0].target
    assert "results.xml" in assertion[0].target
    assert "{workspace}/.wb_bench/results.xml" in assertion[0].target
    assert assertion[0].result_file == "{workspace}/.wb_bench/results.xml"
    assert len(assertion[0].readonly_paths) == 1
    # Harbor /tests/grading and /tests/gold mounts are rewritten to the source
    # cache absolute paths (no bare /tests/... / /logs/verifier/ roots remain).
    assert str(task_dir / "tests" / "grading") in assertion[0].target
    assert "WB_BENCH_GOLD_PATH" in assertion[0].target
    assert "WB_BENCH_FIXTURES_DIR" in assertion[0].target
    assert "/logs/verifier/" not in assertion[0].target
    assert Path(assertion[0].readonly_paths[0]).is_dir()


@pytest.mark.asyncio
async def test_office_verifier_grading_full_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Office grading run passes end to end through the real executor."""
    import sys

    from myrm_agent_harness.eval.assertions import evaluate_sandbox_assertions
    from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
    from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
    from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import (
        NullProvider,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import (
        SandboxStatus,
    )

    _null_result = (
        NullProvider(),
        SandboxStatus(enabled=False, provider_name="null", reason="test"),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        lambda **_kwargs: _null_result,
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
        lambda **_kwargs: _null_result,
    )
    config = ExecutionConfig()
    config.local.shared_venv_path = sys.prefix
    executor = LocalExecutor(config)

    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "office", ["t1"], office_grading=True
    )
    subset = wb._SUBSET_BY_ID["office"]
    task_dir = next(source_root.glob("tasks/*"))
    workspace = wbw._prepare_workspace(task_dir, subset)
    assert workspace is not None
    case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assertion = case.turns[0].sandbox_assertions
    assert len(assertion) == 1

    executor.bind_workspace(str(workspace))
    scores: dict[str, float] = {}
    passed, details = await evaluate_sandbox_assertions(
        assertion, executor, scores_out=scores
    )
    assert passed is True, details
    assert scores["pass_rate"] == 1.0
    assert (workspace / ".wb_bench" / "results.xml").exists()


def test_sec_direct_scorer_injects_reward_assertion(tmp_path: Path) -> None:
    """Security tasks scored by tests/scoring.py get a reward.json assertion."""
    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "sec", ["t1"], direct_scorer="scoring.py"
    )
    subset = wb._SUBSET_BY_ID["sec"]
    task_dir = next(source_root.glob("tasks/*"))

    workspace = wbw._prepare_workspace(task_dir, subset)
    assert workspace is not None
    case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assertion = case.turns[0].sandbox_assertions
    assert len(assertion) == 1
    assert assertion[0].type == "test_suite"
    assert "scoring.py" in assertion[0].target
    assert assertion[0].result_file == "{workspace}/reward.json"
    assert len(assertion[0].readonly_paths) == 1
    assert Path(assertion[0].readonly_paths[0]).is_dir()


def test_sec_test_outputs_alt_scorer(tmp_path: Path) -> None:
    """tests/test_outputs.py is recognized as the Security direct scorer."""
    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "sec", ["t1"], direct_scorer="test_outputs.py"
    )
    task_dir = next(source_root.glob("tasks/*"))
    subset = wb._SUBSET_BY_ID["sec"]

    workspace = wbw._prepare_workspace(task_dir, subset)
    case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assertion = case.turns[0].sandbox_assertions
    assert len(assertion) == 1
    assert "test_outputs.py" in assertion[0].target


@pytest.mark.asyncio
async def test_sec_direct_scorer_full_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Security scorer writing reward.json grades end to end."""
    import sys

    from myrm_agent_harness.eval.assertions import evaluate_sandbox_assertions
    from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
    from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
    from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import (
        NullProvider,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import (
        SandboxStatus,
    )

    _null_result = (
        NullProvider(),
        SandboxStatus(enabled=False, provider_name="null", reason="test"),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        lambda **_kwargs: _null_result,
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
        lambda **_kwargs: _null_result,
    )
    config = ExecutionConfig()
    config.local.shared_venv_path = sys.prefix
    executor = LocalExecutor(config)

    source_root = _write_fake_subset(
        wb.SOURCES_DIR, "sec", ["t1"], direct_scorer="scoring.py"
    )
    subset = wb._SUBSET_BY_ID["sec"]
    task_dir = next(source_root.glob("tasks/*"))
    workspace = wbw._prepare_workspace(task_dir, subset)
    assert workspace is not None
    case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
    assertion = case.turns[0].sandbox_assertions
    assert len(assertion) == 1

    executor.bind_workspace(str(workspace))
    scores: dict[str, float] = {}
    passed, details = await evaluate_sandbox_assertions(
        assertion, executor, scores_out=scores
    )
    assert passed is True, details
    assert scores["pass_rate"] == 1.0
    assert (workspace / "reward.json").exists()


class TestVerifierTomlGradingE2E:
    """Full grading path: source-cache read-only mount + {workspace} → verdict.

    These tests exercise the real sandboxed executor end to end (no LLM):
    the ``script_verifier`` command generated by ``_test_suite_assertion_for``
    runs verifier.py from the read-only source cache against the seeded agent
    workspace and the numeric reward.txt it writes drives the verdict.
    """

    @pytest.fixture(autouse=True)
    def _local_executor(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Wire a real LocalExecutor with the null sandbox provider (test env)."""
        import sys

        from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
        from myrm_agent_harness.toolkits.code_execution.executors.local import (
            LocalExecutor,
        )
        from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import (
            NullProvider,
        )
        from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import (
            SandboxStatus,
        )

        _null_result = (
            NullProvider(),
            SandboxStatus(enabled=False, provider_name="null", reason="test"),
        )

        def _fake(**_kwargs):
            return _null_result

        monkeypatch.setattr(
            "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
            _fake,
        )
        monkeypatch.setattr(
            "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
            _fake,
        )
        config = ExecutionConfig()
        config.local.shared_venv_path = sys.prefix
        self.executor = LocalExecutor(config)
        self.executor.bind_workspace(str(tmp_path / "agent_ws"))
        (tmp_path / "agent_ws").mkdir(parents=True, exist_ok=True)

    @pytest.mark.asyncio
    async def test_script_verifier_full_grading_path(self, tmp_path: Path) -> None:
        """A passing verifier yields reward 1.0 through the real executor."""
        from myrm_agent_harness.eval.assertions import evaluate_sandbox_assertions

        source_root = _write_fake_subset(
            wb.SOURCES_DIR, "code", ["t1"], verifier_family="script_verifier"
        )
        subset = wb._SUBSET_BY_ID["code"]
        task_dir = next(source_root.glob("tasks/*"))
        workspace = wbw._prepare_workspace(task_dir, subset)
        assert workspace is not None
        case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
        assertion = case.turns[0].sandbox_assertions
        assert len(assertion) == 1

        # The seeded workspace holds the task file; verifier.py writes the
        # bare numeric reward.txt into the workspace via the LOG_DIR contract.
        self.executor.bind_workspace(str(workspace))
        scores: dict[str, float] = {}
        passed, details = await evaluate_sandbox_assertions(
            assertion, self.executor, scores_out=scores
        )
        assert passed is True, details
        assert scores["pass_rate"] == 1.0
        assert (workspace / ".wb_bench" / "logs" / "reward.txt").exists()
        # Gold patch never lands in the agent workspace.
        assert not (workspace / "gold.patch").exists()

    @pytest.mark.asyncio
    async def test_verifier_absent_agent_failure_low_reward(
        self, tmp_path: Path
    ) -> None:
        """A verifier grading a broken workspace yields a sub-1.0 reward."""
        from myrm_agent_harness.eval.assertions import evaluate_sandbox_assertions

        source_root = _write_fake_subset(
            wb.SOURCES_DIR, "code", ["t1"], verifier_family="script_verifier"
        )
        task_dir = next(source_root.glob("tasks/*"))
        subset = wb._SUBSET_BY_ID["code"]
        workspace = wbw._prepare_workspace(task_dir, subset)
        assert workspace is not None
        # Simulate a failed agent: the graded artifact is gone.
        (workspace / "app.py").unlink()
        case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)

        self.executor.bind_workspace(str(workspace))
        scores: dict[str, float] = {}
        passed, details = await evaluate_sandbox_assertions(
            case.turns[0].sandbox_assertions, self.executor, scores_out=scores
        )
        assert passed is False
        assert scores["pass_rate"] < 1.0
        assert "Sandbox assertion failed" in details

    @pytest.mark.asyncio
    async def test_pytest_injected_full_grading_path(self, tmp_path: Path) -> None:
        """pytest_injected: injected tests run and JUnit XML drives the verdict."""
        from myrm_agent_harness.eval.assertions import evaluate_sandbox_assertions

        source_root = _write_fake_subset(
            wb.SOURCES_DIR, "code", ["t1"], verifier_family="pytest_injected"
        )
        subset = wb._SUBSET_BY_ID["code"]
        task_dir = next(source_root.glob("tasks/*"))
        workspace = wbw._prepare_workspace(task_dir, subset)
        assert workspace is not None
        case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
        assertion = case.turns[0].sandbox_assertions
        assert len(assertion) == 1

        # Injected tests are copied from the read-only source cache into the
        # workspace, then the declared pytest command runs and writes the JUnit
        # report into {workspace}/.wb_bench/results.xml.
        self.executor.bind_workspace(str(workspace))
        scores: dict[str, float] = {}
        passed, details = await evaluate_sandbox_assertions(
            assertion, self.executor, scores_out=scores
        )
        assert passed is True, details
        assert scores["pass_rate"] == 1.0
        assert (workspace / ".wb_bench" / "results.xml").exists()
        # Injected tests land only in the workspace copy, never in the cache.
        assert not (workspace / "gold.patch").exists()

    @pytest.mark.asyncio
    async def test_pytest_injected_failing_test_low_reward(
        self, tmp_path: Path
    ) -> None:
        """A failing injected test yields a sub-1.0 reward via JUnit parsing."""
        from myrm_agent_harness.eval.assertions import evaluate_sandbox_assertions

        source_root = _write_fake_subset(
            wb.SOURCES_DIR, "code", ["t1"], verifier_family="pytest_injected"
        )
        # The injected test now asserts against a graded artifact that the agent
        # workspace does not provide → the grading run reports a failure.
        (
            source_root
            / "tasks"
            / "t1"
            / "tests"
            / "injected"
            / "tests"
            / "test_app.py"
        ).write_text("def test_ok(): assert False\n")
        subset = wb._SUBSET_BY_ID["code"]
        task_dir = next(source_root.glob("tasks/*"))
        workspace = wbw._prepare_workspace(task_dir, subset)
        assert workspace is not None
        case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)

        self.executor.bind_workspace(str(workspace))
        scores: dict[str, float] = {}
        passed, details = await evaluate_sandbox_assertions(
            case.turns[0].sandbox_assertions, self.executor, scores_out=scores
        )
        assert passed is False
        assert scores["pass_rate"] == 0.0
        assert "Sandbox assertion failed" in details

    @pytest.mark.asyncio
    async def test_repo_understanding_full_grading_path(self, tmp_path: Path) -> None:
        """repo_understanding: scorer.py grades the repo and writes reward.json."""
        from myrm_agent_harness.eval.assertions import evaluate_sandbox_assertions

        source_root = _write_fake_subset(
            wb.SOURCES_DIR, "code", ["t1"], verifier_family="repo_understanding"
        )
        subset = wb._SUBSET_BY_ID["code"]
        task_dir = next(source_root.glob("tasks/*"))
        workspace = wbw._prepare_workspace(task_dir, subset)
        assert workspace is not None
        case = wbw._case_for_task(task_dir, subset, workspace_dir=workspace)
        assertion = case.turns[0].sandbox_assertions
        assert len(assertion) == 1

        # scorer.py runs from the read-only source cache against the seeded repo
        # and writes the numeric reward into {workspace}/.wb_bench/reward.json.
        self.executor.bind_workspace(str(workspace))
        scores: dict[str, float] = {}
        passed, details = await evaluate_sandbox_assertions(
            assertion, self.executor, scores_out=scores
        )
        assert passed is True, details
        assert scores["pass_rate"] == 1.0
        assert (workspace / ".wb_bench" / "reward.json").exists()
        assert not (workspace / "gold.patch").exists()


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


def test_iter_task_dirs_missing_tasks_root_returns_empty(tmp_path: Path) -> None:
    empty_root = tmp_path / "src"
    empty_root.mkdir()
    assert wbw._iter_task_dirs(empty_root) == []


def test_read_instruction_fallback_when_missing(tmp_path: Path) -> None:
    task_dir = tmp_path / "task_x"
    task_dir.mkdir()
    text = wbw._read_instruction(task_dir)
    assert "task_x" in text


def test_prepare_workspace_cleans_stale_stage_and_cache(tmp_path: Path) -> None:
    """A stale extraction stage and previous cache are removed before reseeding."""
    source_root = _write_fake_subset(wb.SOURCES_DIR, "code", ["t1"])
    task_dir = next(source_root.glob("tasks/*"))
    subset = wb._SUBSET_BY_ID["code"]

    assert wbw._prepare_workspace(task_dir, subset) is not None
    cache_root = wbw.WORKSPACES_DIR / subset.id
    cache_dir = cache_root / task_dir.name
    # Plant a stale stage and a stale cache, then drop the readiness marker so
    # the next call re-runs the extraction cleanup branches.
    (cache_root / f".stage-{task_dir.name}" / "junk").mkdir(parents=True)
    (cache_dir / "workspace" / "junk.txt").write_text("stale")
    (cache_dir / ".ready").unlink()

    ws = wbw._prepare_workspace(task_dir, subset)
    assert ws is not None
    assert (ws / "app.py").exists()
    assert not (cache_root / f".stage-{task_dir.name}").exists()


def test_build_cases_unknown_subset_raises() -> None:
    with pytest.raises(ValueError, match="Unknown WBBench subset"):
        wbw.build_wb_bench_cases("nonexistent")


def test_build_cases_no_tasks_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An installed subset with no runnable tasks raises a clear error."""

    async def _fake_ensure(*args: object, **kwargs: object) -> Path:
        return tmp_path

    monkeypatch.setattr(
        "app.core.eval.wb_bench.download.ensure_wb_bench_source", _fake_ensure
    )
    monkeypatch.setattr(wbw, "_iter_task_dirs", lambda source_root: [])
    with pytest.raises(ValueError, match="No runnable tasks"):
        wbw.build_wb_bench_cases("code")


def test_build_cases_full_success_path_seeds_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full build path maps tasks, seeds workspaces and logs the summary."""
    source_root = _write_fake_subset(
        tmp_path, "code", ["t1"], verifier_family="script_verifier"
    )

    async def _fake_ensure(*args: object, **kwargs: object) -> Path:
        return source_root

    monkeypatch.setattr(
        "app.core.eval.wb_bench.download.ensure_wb_bench_source", _fake_ensure
    )
    cases, seed_map = wbw.build_wb_bench_cases("code")
    assert len(cases) == 1
    assert len(seed_map) == 1
    assert cases[0].metadata["wb_bench_task_id"] == "t1"
    assert next(iter(seed_map.values())) == str(
        wbw.WORKSPACES_DIR / "code" / "t1" / "workspace"
    )


def test_full_build_requires_real_subset(tmp_path: Path) -> None:
    """build_wb_bench_cases without a local download raises (network is mocked off)."""
    with (
        patch("app.core.eval.wb_bench.download.httpx.Client") as mock_client,
        patch("app.core.eval.wb_bench.download.httpx.AsyncClient") as mock_async,
    ):
        mock_client.return_value.__enter__.return_value.get.side_effect = OSError(
            "offline"
        )
        mock_async.side_effect = OSError("offline")
        with pytest.raises((OSError, ValueError)):
            wbw.build_wb_bench_cases("code")


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
