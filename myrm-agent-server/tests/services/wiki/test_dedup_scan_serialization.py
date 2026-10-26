"""Scans of one vault run one after another: overlapping scans cannot multiply groups or let an older snapshot win."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import scanner as scanner_module

from app.services.wiki import dedup_runner
from app.services.wiki.dedup_runner import list_wiki_dedup_groups, run_wiki_dedup_scan_job
from tests.support.wiki_compile_probe import isolated_wiki_vault, write_raw

_OLDER_SCAN = "older-scan"


@pytest.fixture
def structure(tmp_path: Path) -> Iterator[WikiStructure]:
    with isolated_wiki_vault(tmp_path) as vault:
        yield vault


def _member_sets() -> list[tuple[str, ...]]:
    return sorted(tuple(member.relative_path for member in group.members) for group in list_wiki_dedup_groups())


def _hold_the_older_scan(monkeypatch: pytest.MonkeyPatch) -> tuple[threading.Event, threading.Event]:
    """Park the thread named ``older-scan`` inside its first fingerprint read until ``resume`` is set."""
    parked = threading.Event()
    resume = threading.Event()
    real = scanner_module.build_fingerprint

    def build_fingerprint(raw_file: Path, *, relative_path: str):
        if threading.current_thread().name == _OLDER_SCAN and not parked.is_set():
            parked.set()
            resume.wait(timeout=30)
        return real(raw_file, relative_path=relative_path)

    monkeypatch.setattr(scanner_module, "build_fingerprint", build_fingerprint)
    return parked, resume


@pytest.mark.parametrize(
    ("older_scope", "fresher_scope"),
    [(None, None), (None, "default"), ("default", None)],
    ids=["same-scope", "implicit-then-named-default", "named-then-implicit-default"],
)
def test_an_older_scan_cannot_overwrite_the_groups_of_a_fresher_one(
    structure: WikiStructure,
    monkeypatch: pytest.MonkeyPatch,
    older_scope: str | None,
    fresher_scope: str | None,
) -> None:
    write_raw(structure, "a.md", "# First\n\nBody of the first pair")
    write_raw(structure, "b.md", "# First\n\nBody of the first pair")
    parked, resume = _hold_the_older_scan(monkeypatch)
    failures: list[BaseException] = []

    def scan(scope: str | None) -> None:
        try:
            dedup_runner._run_scan_sync(agent_id=scope, incremental=False)
        except BaseException as exc:
            failures.append(exc)

    older = threading.Thread(target=scan, args=(older_scope,), name=_OLDER_SCAN)
    older.start()
    assert parked.wait(timeout=10)

    write_raw(structure, "c.md", "# Second\n\nBody of the second pair")
    write_raw(structure, "d.md", "# Second\n\nBody of the second pair")
    fresher = threading.Thread(target=scan, args=(fresher_scope,), name="fresher-scan")
    fresher.start()
    # Unserialized, the fresher scan finishes in this window and the older one then overwrites it.
    fresher.join(timeout=0.5)
    resume.set()
    older.join(timeout=30)
    fresher.join(timeout=30)

    assert not failures
    assert not older.is_alive()
    assert not fresher.is_alive()
    assert _member_sets() == [("a.md", "b.md"), ("c.md", "d.md")]


async def test_overlapping_scan_jobs_leave_each_duplicate_group_once(structure: WikiStructure) -> None:
    pairs = 30
    for index in range(pairs):
        body = f"# Doc {index}\n\nBody number {index} " + "x" * index
        write_raw(structure, f"set{index}/a.md", body)
        write_raw(structure, f"set{index}/b.md", body)

    results = await asyncio.gather(*(run_wiki_dedup_scan_job(incremental=False) for _ in range(4)))

    assert not any(result.skipped for result in results)
    assert len(_member_sets()) == pairs
