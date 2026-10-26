"""Real-vault probes for duplicate-review tests: an isolated vault, a model that records being reached, queue helpers.

[INPUT]
- app.services.wiki.vault (POS: vault path resolution and the shared archiver cache)
- myrm_agent_harness.toolkits.wiki (POS: vault layout, ingestion queue and the compile worker slots)

[OUTPUT]
- isolated_wiki_vault: point the wiki root at a temp dir with a clean archiver cache and clean worker slots
- ReachableModel: chat-model stand-in that records the attributes the compile pipeline reaches for
- clear_compile_workers / wait_until_queue_idle: simulate an idled-out worker, wait for a queue to drain
- write_raw / write_concept / seed_open_group: build raw files, a compiled page citing them, a scanned duplicate group

[POS]
Lets tests drive the real archiver, compile worker and dedup store instead of mocks, so wiring mistakes (a compile
worker built without a model, a group table half written) surface as the failures users would see.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from myrm_agent_harness.toolkits.wiki import WikiIngestionQueue, WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.compiler import WikiCompiler
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
    CorpusDedupScanner,
    DuplicateGroup,
    GroupStatus,
)

DUPLICATE_BODY = "# Quarterly report\n\nThe very same text, imported twice."


class ReachableModel:
    """Stand-in for the user's chat model: building the pipeline touches nothing, compiling reaches for ``ainvoke``."""

    def __init__(self) -> None:
        self.reached: list[str] = []

    def __getattr__(self, name: str) -> object:
        if name.startswith("__"):
            raise AttributeError(name)
        self.reached.append(name)
        raise RuntimeError(f"model reached via {name}")


def clear_compile_workers() -> None:
    """Drop every compile worker slot, as when each worker has idled out."""
    for task in WikiCompiler._active_workers.values():
        try:
            task.cancel()
        except RuntimeError:
            # The task belongs to an event loop that an earlier test already closed.
            continue
    WikiCompiler._active_workers.clear()


@contextmanager
def isolated_wiki_vault(root: Path) -> Iterator[WikiStructure]:
    """Point the wiki root at ``root`` and yield the default agent's vault layout."""
    from app.services.wiki.vault import reset_wiki_archiver_cache_for_tests

    reset_wiki_archiver_cache_for_tests()
    clear_compile_workers()
    with patch("app.services.wiki.vault.resolver.wiki_root", return_value=root / "wiki"):
        structure = WikiStructure(root / "wiki" / "agents" / "default")
        structure.ensure_structure()
        try:
            yield structure
        finally:
            clear_compile_workers()
            reset_wiki_archiver_cache_for_tests()


async def wait_until_queue_idle(structure: WikiStructure, *, timeout_s: float = 15.0) -> dict[str, int]:
    """Wait until nothing is pending or processing and return the final queue counts."""
    queue = WikiIngestionQueue(structure)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        stats = queue.get_stats()
        if stats["pending"] + stats["processing"] == 0:
            return stats
        if loop.time() >= deadline:
            raise AssertionError(f"compile queue still busy after {timeout_s}s: {stats}")
        await asyncio.sleep(0.05)


def write_raw(structure: WikiStructure, relative_path: str, content: str) -> Path:
    path = structure.get_raw_file_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_concept(structure: WikiStructure, name: str, *, sources: list[str]) -> Path:
    """Write a compiled page that cites ``sources``, so removing one of them re-queues the others."""
    path = structure.get_concept_file_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    listing = "\n".join(f"  - {source}" for source in sources)
    path.write_text(f"---\nsources:\n{listing}\n---\n# {name}\n\nCompiled from the sources above.\n", encoding="utf-8")
    return path


def seed_open_group(structure: WikiStructure, *paths: str, content: str = DUPLICATE_BODY) -> DuplicateGroup:
    """Write identical raw files at ``paths``, scan from scratch and return the one open group."""
    for relative_path in paths:
        write_raw(structure, relative_path, content)
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    (group,) = scanner.store.list_groups(status=GroupStatus.OPEN)
    return group
