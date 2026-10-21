"""Live end-to-end tests for the WorkBuddy Bench download chain.

These tests run the real download -> checksum verify -> atomic install ->
workspace provisioning pipeline against the public HuggingFace dataset
(``tencent/workbuddy-bench``). No core download/verify/extract logic is
mocked; the only fixture-level indirection is redirecting WBBench storage into
a per-test temp dir so the repo tree is never polluted.

The ``office`` subset (~10 MB, 50 tasks) is the smallest archive and keeps
every case well under the integration time budget. Requires network access to
``huggingface.co`` and is marked ``e2e`` so it is excluded from the default
suite.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.eval import wb_bench
from app.core.eval.wb_bench import DownloadAbortedError


@pytest.fixture(autouse=True)
def _isolated_wb_bench(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect WBBench storage into a per-test temp dir (never the repo)."""
    monkeypatch.chdir(tmp_path)


@pytest.mark.e2e
def test_download_install_build_office_live() -> None:
    """Real end-to-end happy path: download, checksum-verify, install, build cases."""
    source_root = asyncio.run(wb_bench.ensure_wb_bench_source("office"))
    assert (source_root / "tasks").is_dir()

    cases, seed_map = wb_bench.build_wb_bench_cases("office")
    assert len(cases) == 50
    assert seed_map, "office tasks should provision seeded workspaces from workspace.tar.gz"
    for case in cases:
        assert case.metadata["wb_bench_scoring"] == "composite"
        assert case.metadata["wb_bench_source"] == "office"


@pytest.mark.e2e
def test_download_idempotent_second_call() -> None:
    """A second ensure call must reuse the installed source without re-downloading."""
    first_root = asyncio.run(wb_bench.ensure_wb_bench_source("office"))
    assert (first_root / "tasks").is_dir()

    second_root = asyncio.run(wb_bench.ensure_wb_bench_source("office"))
    assert second_root == first_root


@pytest.mark.e2e
def test_download_abort_midstream_live() -> None:
    """A real download interrupted mid-stream raises and leaves no partial file."""
    abort = {"flag": False}

    def progress(_downloaded: int, _total: int) -> None:
        abort["flag"] = True

    with pytest.raises(DownloadAbortedError):
        asyncio.run(
            wb_bench.ensure_wb_bench_source(
                "office",
                progress_callback=progress,
                should_abort=lambda: abort["flag"],
            )
        )
    assert not list(wb_bench.ARCHIVES_DIR.glob("*.part"))


@pytest.mark.e2e
def test_download_abort_before_stream() -> None:
    """An abort already requested before streaming surfaces immediately."""
    with pytest.raises(DownloadAbortedError):
        asyncio.run(wb_bench.ensure_wb_bench_source("office", should_abort=lambda: True))
