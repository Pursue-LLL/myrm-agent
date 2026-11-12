"""Physical-memory footprint of the Next dev server's process tree.

[INPUT]
  frontend_lifecycle.process_tree::snapshot / descendants (POS: read-only observation primitives
  over ps(1) parent links);
  e2e_core.proc_footprint::platform_reader / FootprintReader (POS: per-process physical
  footprint, libproc on macOS and /proc on Linux);
  dev_gate.contract::FRONTEND_FOOTPRINT_LIMIT_MB (POS: SSOT for the dev server's memory ceiling,
  overridden by MYRM_FRONTEND_FOOTPRINT_LIMIT_MB);
  frontend_lifecycle.policy::env_float (POS: positive-float env parsing with a default)

[OUTPUT]
  Measurement / measure() / limit_bytes()

[POS]
  Evidence for the dev supervisor's memory guard (scripts/next-supervisor.ts). The tree is
  summed in physical footprint, not RSS, because compressed and swapped pages leave RSS yet
  still weigh on the machine (one Bun-hosted Next server measured 2.7-8.5 GB RSS against
  ~22 GB footprint). On Linux the per-process figure is RSS, so shared pages count once per
  process in the tree sum.
"""

from __future__ import annotations

from dataclasses import dataclass

from dev_gate.contract import FRONTEND_FOOTPRINT_LIMIT_MB
from e2e_core.proc_footprint import FootprintReader, platform_reader

from frontend_lifecycle import process_tree
from frontend_lifecycle.policy import env_float

LIMIT_ENV = "MYRM_FRONTEND_FOOTPRINT_LIMIT_MB"
_BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class Measurement:
    root_pid: int
    pids: tuple[int, ...]
    footprint_bytes: int
    limit_bytes: int

    @property
    def exceeded(self) -> bool:
        return self.footprint_bytes > self.limit_bytes

    def render(self) -> str:
        return (
            f"FOOTPRINT pid={self.root_pid} procs={len(self.pids)} "
            f"mb={self.footprint_bytes // _BYTES_PER_MB} "
            f"limit_mb={self.limit_bytes // _BYTES_PER_MB}"
        )


def limit_bytes() -> int:
    mb = env_float(LIMIT_ENV, float(FRONTEND_FOOTPRINT_LIMIT_MB))
    return int(mb * _BYTES_PER_MB)


def measure(
    root_pid: int,
    *,
    reader: FootprintReader | None = None,
    samples: dict[int, process_tree.ProcSample] | None = None,
    limit: int | None = None,
) -> Measurement | None:
    """Footprint of ``root_pid`` and every descendant; None when it cannot be measured.

    A process that exits between the ``ps`` snapshot and its read contributes nothing:
    the figure is a lower bound taken at one instant, which is all a ceiling check needs.
    """
    read = reader or platform_reader()
    if read is None:
        return None
    tree = process_tree.descendants(
        process_tree.snapshot() if samples is None else samples, [root_pid]
    )
    if root_pid not in tree:
        return None
    readings = {pid: read(pid) for pid in sorted(tree)}
    return Measurement(
        root_pid=root_pid,
        pids=tuple(pid for pid, size in readings.items() if size is not None),
        footprint_bytes=sum(size for size in readings.values() if size is not None),
        limit_bytes=limit_bytes() if limit is None else limit,
    )
