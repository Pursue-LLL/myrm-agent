"""Hold freshly published raw files back from the compile queue until the duplicate scan has looked at them.

[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup::CorpusDedupGovernor (POS: open duplicate groups that block compiling)
- myrm_agent_harness.toolkits.wiki::WikiStructure (POS: raw/ root the group member paths are relative to)

[OUTPUT]
- DeferredCompileEnqueue: ``enqueue_file`` stand-in that records paths; ``release`` queues the ones no open exact/normalized group claims once a scan has completed

[POS]
Connectors call ``compiler_enqueue.enqueue_file(path)`` the moment a file is written, long before the post-run dedup
scan can say whether it is a copy. Handing them this object instead of the compiler defers only that call: the entry
point scans, then releases, so identical documents are not compiled (and billed) twice. Members of an open group wait
for the user in Duplicate Review. When the scan did not complete (it is skipped while a compile is running, or it
failed) the stored groups say nothing reliable about the new files, so every held file is released: a document is never
dropped.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupGovernor

logger = logging.getLogger(__name__)


class FileEnqueuer(Protocol):
    def enqueue_file(self, file_path: Path) -> None: ...


class DeferredCompileEnqueue:
    def __init__(self, compiler: FileEnqueuer, structure: WikiStructure) -> None:
        self._compiler = compiler
        self._structure = structure
        self._pending: dict[Path, None] = {}

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def enqueue_file(self, file_path: Path) -> None:
        self._pending[file_path] = None

    def release(self, *, scan_completed: bool) -> int:
        """Queue the held files and return how many were queued.

        After a completed scan, members of an open exact/normalized group stay out; without one every file is queued.
        """
        pending, self._pending = list(self._pending), {}
        held = self._blocked_relative_paths() if pending and scan_completed else frozenset()
        queued = 0
        for path in pending:
            if self._relative_path(path) in held:
                continue
            try:
                self._compiler.enqueue_file(path)
            except Exception as exc:
                logger.warning("Auto-compile enqueue failed for %s: %s", path.name, exc)
            else:
                queued += 1
        return queued

    def _blocked_relative_paths(self) -> frozenset[str]:
        try:
            groups = CorpusDedupGovernor(self._structure).blocking_open_groups()
        except Exception as exc:
            logger.warning("Duplicate groups unavailable, releasing every held file: %s", exc)
            return frozenset()
        return frozenset(member.relative_path for group in groups for member in group.members)

    def _relative_path(self, file_path: Path) -> str | None:
        try:
            return file_path.relative_to(self._structure.raw_dir).as_posix()
        except ValueError:
            return None
