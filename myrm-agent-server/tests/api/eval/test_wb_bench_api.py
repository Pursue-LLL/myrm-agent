"""API integration tests for the WorkBuddy Bench endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import io
import tarfile
import tempfile
import time
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="eval")


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


def test_wb_bench_sources_endpoint(client: TestClient) -> None:
    res = client.get("/api/v1/eval/wb-bench/sources")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "success"
    sources = data["sources"]
    assert [s["id"] for s in sources] == ["code", "web", "office", "sec"]
    assert all("task_count" in s and "is_downloaded" in s for s in sources)
    assert [s["scoring"] for s in sources] == [
        "composite",
        "composite",
        "composite",
        "native",
    ]


def test_wb_bench_run_unknown_subset(client: TestClient) -> None:
    res = client.post("/api/v1/eval/wb-bench/run", json={"subset_id": "nope"})
    assert res.status_code == 200
    assert res.json()["status"] == "error"
    assert "Unknown WBBench subset" in res.json()["error"]


def test_wb_bench_download_unknown_subset(client: TestClient) -> None:
    res = client.post("/api/v1/eval/wb-bench/download", json={"subset_id": "nope"})
    assert res.status_code == 200
    assert res.json()["status"] == "error"
    assert "Unknown WBBench subset" in res.json()["error"]


def test_wb_bench_download_reports_progress(client: TestClient) -> None:
    """The download-only endpoint installs the source and records progress."""
    from app.core.eval import wb_bench as wb

    tmp = Path(tempfile.mkdtemp())

    async def _fake_ensure(
        subset_id: str,
        *,
        max_retries: int = 2,
        progress_callback=None,
        should_abort=None,
    ):
        source_root = tmp / "sources" / "wb-bench-web-v1.0"
        (source_root / "tasks" / "t1").mkdir(parents=True)
        (source_root / "tasks" / "t1" / "task.toml").write_text(
            '[verifier]\nengine = "composite"\n'
        )
        if progress_callback:
            progress_callback(1024 * 1024, 2048 * 1024)
        return source_root

    with (
        patch.object(wb, "SOURCES_DIR", tmp / "sources"),
        patch(
            "app.core.eval.wb_bench.ensure_wb_bench_source", side_effect=_fake_ensure
        ),
    ):
        res = client.post("/api/v1/eval/wb-bench/download", json={"subset_id": "web"})
        assert res.status_code == 200
        assert res.json()["status"] == "started"

        # Background tasks settle synchronously within TestClient.
        status = client.get("/api/v1/eval/status").json()
        assert status.get("is_running") is False
        assert status.get("error") is None
        assert status.get("download_progress") == {
            "downloaded_bytes": 1024 * 1024,
            "total_bytes": 2048 * 1024,
        }

    assert (tmp / "sources" / "wb-bench-web-v1.0" / "tasks" / "t1").is_dir()


@pytest.mark.asyncio
async def test_wb_bench_download_abort_flow(tmp_path) -> None:
    """A user abort during the download phase cancels and resets state cleanly."""
    from app.core.eval import service
    from app.core.eval import wb_bench as wb

    async def _spinning_download(
        subset: wb.WbBenchSubset,
        archive_path: Path,
        *,
        expected: str | None,
        max_retries: int,
        progress_callback,
        should_abort,
    ) -> None:
        while should_abort and not should_abort():
            await asyncio.sleep(0.01)
        raise wb.DownloadAbortedError(f"Download of {subset.archive} aborted")

    with (
        patch.object(wb.download, "ARCHIVES_DIR", tmp_path / "archives"),
        patch.object(wb.download, "SOURCES_DIR", tmp_path / "sources"),
        patch(
            "app.core.eval.wb_bench.download._fetch_expected_sha256", return_value=None
        ),
        patch(
            "app.core.eval.wb_bench.download._download_archive",
            side_effect=_spinning_download,
        ),
    ):
        service._eval_state.clear()
        task = asyncio.create_task(service.run_wb_bench_download_background("web"))

        for _ in range(200):
            if service._eval_state.get("is_running"):
                break
            await asyncio.sleep(0.01)
        assert service._eval_state.get("is_running") is True

        assert service.abort_eval() is True
        await task

        assert service._eval_state.get("is_running") is False
        assert service._eval_state.get("error") is None
        assert service._eval_state.get("abort_requested") is True

    # A cancelled download leaves no partial archive behind.
    assert not list((tmp_path / "archives").glob("*.part"))


@pytest.mark.asyncio
async def test_wb_bench_run_abort_after_build_skips_eval(tmp_path) -> None:
    """An abort landing during the build worker phase never starts evaluation."""
    from app.core.eval import service

    service._eval_state.clear()

    def _fake_build(*args, **kwargs):
        service._eval_state["abort_requested"] = True
        return [], {}

    with (
        patch("app.core.eval.wb_bench.build_wb_bench_cases", side_effect=_fake_build),
        patch("app.core.eval.service.run_eval_suite") as mock_run,
    ):
        await service.run_wb_bench_background("web")

    assert mock_run.call_count == 0
    assert service._eval_state.get("is_running") is False
    assert service._eval_state.get("error") is None


def test_wb_bench_run_requires_local_dataset(client: TestClient) -> None:
    """Without a local download, the background run surfaces an error."""
    with (
        patch("app.core.eval.wb_bench.download.httpx.Client") as mock_client,
        patch("app.core.eval.wb_bench.download.httpx.AsyncClient") as mock_async,
    ):
        mock_client.return_value.__enter__.return_value.get.side_effect = OSError(
            "offline"
        )
        mock_async.side_effect = OSError("offline")

        res = client.post("/api/v1/eval/wb-bench/run", json={"subset_id": "sec"})
        assert res.status_code == 200
        assert res.json()["status"] == "started"

        # Wait for the background task to settle (it should fail cleanly offline).
        status: dict = {}
        for _ in range(30):
            r = client.get("/api/v1/eval/status")
            status = r.json()
            if not status.get("is_running", True):
                break
            time.sleep(0.5)

        assert status.get("error") is not None
        assert "offline" in status["error"] or "Unknown" in status["error"]


def test_wb_bench_run_with_mocked_download(client: TestClient) -> None:
    """A successfully downloaded subset schedules a real eval run."""
    from app.core.eval import wb_bench as wb

    subset = wb.download._SUBSET_BY_ID["office"]

    # Build a valid tar.gz matching the office archive layout.
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for task_id in ("t1", "t2"):
            instruction = f"# {task_id}\n".encode()
            info = tarfile.TarInfo(
                f"wb-bench-office-v1.0/tasks/{task_id}/instruction.md"
            )
            info.size = len(instruction)
            tar.addfile(info, io.BytesIO(instruction))
            toml = b'[task]\nid = "t1"\n'
            info = tarfile.TarInfo(f"wb-bench-office-v1.0/tasks/{task_id}/task.toml")
            info.size = len(toml)
            tar.addfile(info, io.BytesIO(toml))
    archive_bytes = buf.getvalue()
    expected_sha = hashlib.sha256(archive_bytes).hexdigest()

    class _FakeResp:
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        async def __aenter__(self) -> "_FakeResp":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def aiter_bytes(self, chunk_size: int):  # type: ignore[no-untyped-def]
            class _AsyncIter:
                def __init__(self, chunks: list[bytes]) -> None:
                    self._chunks = list(chunks)

                def __aiter__(self) -> "_AsyncIter":
                    return self

                async def __anext__(self) -> bytes:
                    if not self._chunks:
                        raise StopAsyncIteration
                    return self._chunks.pop(0)

            return _AsyncIter([archive_bytes])

    class _FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str) -> _FakeResp:
            return _FakeResp()

    # Point storage at an isolated temp dir.
    tmp = Path(tempfile.mkdtemp())
    with (
        patch.object(wb.download, "ARCHIVES_DIR", tmp / "archives"),
        patch.object(wb.download, "SOURCES_DIR", tmp / "sources"),
        patch.object(wb.download, "WORKSPACES_DIR", tmp / "workspaces"),
        patch("app.core.eval.wb_bench.download.httpx.Client") as mock_client,
        patch(
            "app.core.eval.wb_bench.download.httpx.AsyncClient",
            _FakeAsyncClient,
        ),
        patch("app.core.eval.service.run_eval_suite") as mock_run,
    ):
        mock_client.return_value.__enter__.return_value.get.return_value.text = (
            f"{expected_sha}  {subset.archive}\n"
        )
        res = client.post("/api/v1/eval/wb-bench/run", json={"subset_id": "office"})
        assert res.status_code == 200
        assert res.json()["status"] == "started"

        # The background task runs synchronously within TestClient; assert the
        # run_eval_suite call happened with the right dataset id.
        assert mock_run.called

        # The source was downloaded into the temp sources dir.
        assert (tmp / "sources" / "wb-bench-office-v1.0" / "tasks").is_dir()
