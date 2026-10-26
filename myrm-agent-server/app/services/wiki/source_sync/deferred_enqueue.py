"""Hold freshly published raw files back from the compile queue until the duplicate scan has looked at them.

[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup::CorpusDedupGovernor, FileEnqueuer (POS: durable compile holds, release rules, enqueue contract)
- myrm_agent_harness.toolkits.wiki::WikiStructure (POS: raw/ root the held paths are relative to)

[OUTPUT]
- DeferredCompileEnqueue: ``enqueue_file`` stand-in that stores a hold; ``needs_scan`` says a scan is owed; ``release`` queues what the finished scan cleared

[POS]
Connectors call ``compiler_enqueue.enqueue_file(path)`` the moment a file is written, long before the post-run dedup
scan can say whether it is a copy. Handing them this object instead of the compiler turns that call into a hold stored
in the vault's dedup database: the entry point scans, then releases, so identical documents are not compiled (and
billed) twice. A hold outlives the run. Members of an open group wait in Duplicate Review and are compiled as soon as
the user resolves it, and holds left by a run that died, or whose queueing failed, are released by the next run: after
its scan when a file is waiting for one, straight away when every hold is already covered by a finished scan. When this
run's scan did not complete, its files are released without it: a document is never dropped or stranded.
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupGovernor, FileEnqueuer

logger = logging.getLogger(__name__)


class DeferredCompileEnqueue:
    def __init__(self, compiler: FileEnqueuer, structure: WikiStructure) -> None:
        self._compiler = compiler
        self._structure = structure
        self._governor = CorpusDedupGovernor(structure)
        self._published: dict[Path, None] = {}

    @property
    def needs_scan(self) -> bool:
        """True while a held file, from this run or an earlier one, was written after the last scan began."""
        try:
            return self._governor.has_unscanned_holds()
        except Exception as exc:
            logger.warning("Compile holds unreadable, scanning in case this run published files: %s", exc)
            return bool(self._published)

    def enqueue_file(self, file_path: Path) -> None:
        relative_path = self._relative_path(file_path)
        if relative_path is not None:
            try:
                self._governor.hold_for_compile([relative_path])
            except Exception as exc:
                logger.warning("Compile hold unavailable for %s, queueing it now: %s", file_path.name, exc)
            else:
                self._published[file_path] = None
                return
        self._enqueue_directly(file_path)

    async def release(self, *, scan_completed: bool) -> int:
        """Queue the held files that may compile now and return how many were queued.

        When a scan has judged every hold (this run's scan completed, or no hold is waiting for one) the covered holds go
        except the members of an open exact or normalized group. Otherwise only this run's files go, whatever the stored
        groups say: they describe an older corpus.
        """
        files = list(self._published)
        judged = scan_completed or not self.needs_scan
        self._published.clear()
        try:
            if judged:
                return await self._governor.release_held(self._compiler)
            relative_paths = [path for file in files if (path := self._relative_path(file)) is not None]
            return await self._governor.release_unguarded(self._compiler, relative_paths)
        except Exception as exc:
            logger.warning("Duplicate check unavailable, queueing this run's files directly: %s", exc)
        return sum(self._enqueue_directly(file) for file in files)

    def _enqueue_directly(self, file_path: Path) -> bool:
        try:
            self._compiler.enqueue_file(file_path)
        except Exception as exc:
            logger.warning("Auto-compile enqueue failed for %s: %s", file_path.name, exc)
            return False
        return True

    def _relative_path(self, file_path: Path) -> str | None:
        try:
            return file_path.relative_to(self._structure.raw_dir).as_posix()
        except ValueError:
            return None
