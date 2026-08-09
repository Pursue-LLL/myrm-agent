"""WorkBuddy Bench dataset adapter for the Eval Lab.

[INPUT]
- httpx: HTTP client for HuggingFace dataset downloads
- myrm_agent_harness.eval::MultiTurnEvalCase, EvalCase, SandboxAssertion

[OUTPUT]
- list_wb_bench_sources(): catalog of the four WorkBuddy Bench subsets
- ensure_wb_bench_source(): download (retry + progress/abort callbacks) + checksum verify + atomic extract
- build_wb_bench_cases(): re-exported from wb_bench_workspace (task -> case mapping)

[POS]
Business-layer adapter that turns the WorkBuddy Bench public benchmark
(Code / Web / Office / Security) into Eval Lab runnable cases. Keeps all
WBBench-specific knowledge out of the harness and the generic eval service:
HuggingFace archive naming, task layout, workspace.tar.gz seeding.

Grading is a two-tier story that stays in the adapter:
- Code / Office: each task ships a pytest suite under ``tests/``; the adapter
  copies it into the seeded workspace as ``.wb_bench/tests`` and injects a
  ``test_suite`` sandbox assertion so the harness Rule judge runs pytest,
  parses the JUnit XML, and yields a numeric pass_rate.
- Security: each task ships a native scorer (``tests/scoring.py`` /
  ``tests/test_outputs.py``) driven by ``tests/test.sh`` that writes
  ``reward.json``; the adapter injects a ``test_suite`` assertion running that
  scorer, and the harness parses the JSON reward.
- Web: graded by the VLM judge pipeline (llm_judge.enabled), so the adapter
  records the mode and ships no rule assertions.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Root directory for all WBBench-local assets (.myrm/wb_bench/{archives,sources,workspaces})
WB_BENCH_ROOT = Path(".myrm/wb_bench")
ARCHIVES_DIR = WB_BENCH_ROOT / "archives"
SOURCES_DIR = WB_BENCH_ROOT / "sources"
WORKSPACES_DIR = WB_BENCH_ROOT / "workspaces"

HF_REPO = "tencent/workbuddy-bench"
HF_ENDPOINT = "https://huggingface.co"
DOWNLOAD_TIMEOUT_S = 120
CHUNK_SIZE = 1024 * 256
# Retry budget for large archives (up to ~500 MB): 3 attempts total.
DOWNLOAD_MAX_RETRIES = 2
DOWNLOAD_BACKOFF_BASE_S = 2


class DownloadAbortedError(RuntimeError):
    """Raised when the user cancels an in-progress WBBench download."""


@dataclass(frozen=True, slots=True)
class WbBenchSubset:
    """Static metadata for one WorkBuddy Bench subset."""

    id: str
    archive: str
    display_name: str
    task_count: int
    approx_size_mb: int
    download_url: str
    checksums_url: str


_SUBSETS: tuple[WbBenchSubset, ...] = (
    WbBenchSubset(
        id="code",
        archive="wb-bench-code-v1.0.tar.gz",
        display_name="WBBench Code",
        task_count=80,
        approx_size_mb=196,
        download_url=f"{HF_ENDPOINT}/datasets/{HF_REPO}/resolve/main/wb-bench-code-v1.0.tar.gz",
        checksums_url=f"{HF_ENDPOINT}/datasets/{HF_REPO}/resolve/main/SHA256SUMS",
    ),
    WbBenchSubset(
        id="web",
        archive="wb-bench-web-v1.0.tar.gz",
        display_name="WBBench Web",
        task_count=70,
        approx_size_mb=22,
        download_url=f"{HF_ENDPOINT}/datasets/{HF_REPO}/resolve/main/wb-bench-web-v1.0.tar.gz",
        checksums_url=f"{HF_ENDPOINT}/datasets/{HF_REPO}/resolve/main/SHA256SUMS",
    ),
    WbBenchSubset(
        id="office",
        archive="wb-bench-office-v1.0.tar.gz",
        display_name="WBBench Office",
        task_count=50,
        approx_size_mb=10,
        download_url=f"{HF_ENDPOINT}/datasets/{HF_REPO}/resolve/main/wb-bench-office-v1.0.tar.gz",
        checksums_url=f"{HF_ENDPOINT}/datasets/{HF_REPO}/resolve/main/SHA256SUMS",
    ),
    WbBenchSubset(
        id="sec",
        archive="wb-bench-sec-v1.0.tar.gz",
        display_name="WBBench Security",
        task_count=60,
        approx_size_mb=479,
        download_url=f"{HF_ENDPOINT}/datasets/{HF_REPO}/resolve/main/wb-bench-sec-v1.0.tar.gz",
        checksums_url=f"{HF_ENDPOINT}/datasets/{HF_REPO}/resolve/main/SHA256SUMS",
    ),
)

_SUBSET_BY_ID = {subset.id: subset for subset in _SUBSETS}

# Public catalog of WBBench subset IDs (for API validation).
WB_BENCH_SUBSETS = frozenset(_SUBSET_BY_ID)


def _subset_root(subset: WbBenchSubset) -> Path:
    return SOURCES_DIR / subset.archive.removesuffix(".tar.gz")


def list_wb_bench_sources() -> list[dict[str, object]]:
    """Return the WBBench subset catalog with local availability flags."""
    result: list[dict[str, object]] = []
    for subset in _SUBSETS:
        local_root = _subset_root(subset)
        archive_path = ARCHIVES_DIR / subset.archive
        result.append(
            {
                "id": subset.id,
                "name": subset.display_name,
                "task_count": subset.task_count,
                "approx_size_mb": subset.approx_size_mb,
                "is_downloaded": (local_root / "tasks").is_dir(),
                "local_size_bytes": archive_path.stat().st_size if archive_path.exists() else 0,
                "scoring": _scoring_mode_for(subset),
            }
        )
    return result


def _fetch_expected_sha256(subset: WbBenchSubset) -> str | None:
    """Fetch the SHA256SUMS manifest from HuggingFace and extract this archive's hash.

    Best-effort: returns None when the manifest is unavailable so a download can
    still proceed (matching the upstream fetch script's soft verification).
    """
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(subset.checksums_url)
            resp.raise_for_status()
            for line in resp.text.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == subset.archive:
                    return parts[0]
    except Exception as exc:  # noqa: BLE001 - network failures degrade gracefully
        logger.warning("Failed to fetch WBBench SHA256SUMS for %s: %s", subset.id, exc)
    return None


def _verify_sha256(path: Path, expected: str | None) -> bool:
    if not expected:
        return True
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest() == expected


def _safe_extract(archive_path: Path, dest_dir: Path) -> None:
    """Extract a tar.gz archive guarding against path traversal."""
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            target = (dest_dir / member.name).resolve()
            if not target.is_relative_to(dest_dir.resolve()):
                raise ValueError(f"Blocked path traversal in archive: {member.name}")
        tar.extractall(dest_dir, filter="data")


def _atomic_install(archive_path: Path, subset: WbBenchSubset) -> Path:
    """Extract the archive to a staging dir then swap it in atomically.

    A mid-extract failure can never leave a half-written dataset in place.
    """
    target = _subset_root(subset)
    if (target / "tasks").is_dir():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / f".stage-{subset.id}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        _safe_extract(archive_path, stage)
        installed = stage / subset.archive.removesuffix(".tar.gz")
        if not installed.exists():
            # The archive may extract a single top-level directory with any name.
            candidates = [p for p in stage.iterdir() if p.is_dir()]
            if len(candidates) != 1:
                raise ValueError(
                    f"Unexpected archive layout for {subset.archive}: {[p.name for p in candidates]}"
                )
            installed = candidates[0]
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(installed), target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


async def ensure_wb_bench_source(
    subset_id: str,
    *,
    max_retries: int = DOWNLOAD_MAX_RETRIES,
    progress_callback: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> Path:
    """Download (if needed), verify, and atomically extract a WBBench subset.

    Returns the extracted source root. When the archive already exists locally
    and the subset is already installed, this is a no-op (offline-friendly).

    ``progress_callback(downloaded_bytes, total_bytes)`` is invoked as the
    archive streams down so the caller can surface download progress; the
    total is 0 when the server does not advertise a Content-Length.
    ``should_abort()`` is polled during the stream; when it returns True the
    download is cancelled and ``DownloadAbortedError`` is raised.

    CPU/IO-heavy sub-operations (checksum manifest fetch, hash verify, atomic
    extract) are dispatched to worker threads so this async API never blocks
    the calling event loop.
    """
    subset = _SUBSET_BY_ID.get(subset_id)
    if not subset:
        raise ValueError(f"Unknown WBBench subset: {subset_id}")

    target = _subset_root(subset)
    if (target / "tasks").is_dir():
        logger.info("WBBench source %s already installed: %s", subset_id, target)
        return target

    archive_path = ARCHIVES_DIR / subset.archive
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)

    expected = await asyncio.to_thread(_fetch_expected_sha256, subset)
    if should_abort and should_abort():
        raise DownloadAbortedError(f"Download of {subset.archive} aborted")
    if archive_path.exists() and await asyncio.to_thread(_verify_sha256, archive_path, expected):
        logger.info("Reusing existing archive for %s", subset_id)
    else:
        logger.info("Downloading WBBench %s (%d MB)…", subset_id, subset.approx_size_mb)
        await _download_archive(
            subset,
            archive_path,
            expected=expected,
            max_retries=max_retries,
            progress_callback=progress_callback,
            should_abort=should_abort,
        )

    return await asyncio.to_thread(_atomic_install, archive_path, subset)


async def _download_archive(
    subset: WbBenchSubset,
    archive_path: Path,
    *,
    expected: str | None,
    max_retries: int,
    progress_callback: Callable[[int, int], None] | None,
    should_abort: Callable[[], bool] | None,
) -> None:
    """Stream-download an archive with checksum verification and bounded retries.

    Transient HTTP/IO failures and checksum mismatches are retried with
    exponential backoff; a corrupt archive is never left on disk (the partial
    file is removed after every attempt). A user abort is never retried and
    surfaces as ``DownloadAbortedError``.
    """
    tmp = archive_path.with_name(f"{archive_path.name}.part")
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(DOWNLOAD_TIMEOUT_S),
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", subset.download_url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", "0") or 0)
                    downloaded = 0
                    with tmp.open("wb") as f:
                        async for chunk in resp.aiter_bytes(CHUNK_SIZE):
                            if should_abort and should_abort():
                                raise DownloadAbortedError(f"Download of {subset.archive} aborted")
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total)
            if await asyncio.to_thread(_verify_sha256, tmp, expected):
                tmp.replace(archive_path)
                return
            last_error = ValueError(f"Checksum mismatch for {subset.archive}")
            logger.warning(
                "Checksum mismatch for %s (attempt %d/%d)",
                subset.id,
                attempt + 1,
                max_retries + 1,
            )
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            logger.warning(
                "Download attempt %d/%d failed for %s: %s",
                attempt + 1,
                max_retries + 1,
                subset.id,
                exc,
            )
        finally:
            tmp.unlink(missing_ok=True)
        if attempt < max_retries:
            await asyncio.sleep(DOWNLOAD_BACKOFF_BASE_S * (2**attempt))
    raise ValueError(
        f"Failed to download {subset.archive} after {max_retries + 1} attempts: {last_error}"
    )


# Subsets whose grading is task-native (each task ships its own scorer run
# inside the seeded workspace) rather than the harness Rule/LLM judge.
_NATIVE_SCORING_SUBSETS = frozenset({"sec"})
_COMPOSITE_SCORING_SUBSETS = frozenset({"code", "web", "office"})


def _scoring_mode_for(subset: WbBenchSubset) -> str:
    """Return the grading mode WBBench applies to a subset.

    Security tasks grade via their own ``tests/scoring.py`` driven by
    ``tests/test.sh`` (task-native, no LLM judge). Code/Office grade through
    the harness Rule judge (task-native pytest suite); Web grades through the
    VLM judge pipeline.
    """
    if subset.id in _NATIVE_SCORING_SUBSETS:
        return "native"
    if subset.id in _COMPOSITE_SCORING_SUBSETS:
        return "composite"
    return "unknown"


# Re-exported so existing ``wb_bench.build_wb_bench_cases`` call sites and test
# patches keep working; the implementation lives in wb_bench_workspace. The
# import stays at the bottom to avoid a module-level cycle (wb_bench_workspace
# imports this module at top level).
from .wb_bench_workspace import build_wb_bench_cases  # noqa: E402, F401
