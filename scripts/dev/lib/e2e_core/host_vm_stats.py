"""Kernel memory-pressure signals for the host load recorder (macOS).

[INPUT]
- /usr/sbin/sysctl: kern.memorystatus_vm_pressure_level (the kernel's own verdict) and
  vm.swapusage
- /usr/bin/vm_stat: compressor page count plus cumulative compression, decompression and
  swap-out counters

[OUTPUT]
- VmSnapshot: one instant's raw readings
- VmSample: levels plus paging rates between two snapshots (stored in every load sample)
- read_vm_snapshot() -> VmSnapshot | None
- parse_snapshot(vm_stat, pressure_level, swap_usage) -> VmSnapshot | None
- vm_sample(previous, current, dt) -> VmSample
- PRESSURE_WARN

[POS]
Free-plus-reclaimable memory cannot see the compressor: a host can report many GB of
"available" pages while the compressor holds tens of GB and the kernel sits at level 2, and
the cost shows up as system CPU and load rather than as any one busy process. The level,
the compressor size and the compression traffic say directly whether a load spike was
memory thrash. Three short commands cost about 10 ms per sample; every failure yields None
and the recorder simply omits the ``vm`` block for that sample.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, TypedDict

# kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical.
PRESSURE_WARN: Final = 2

_VM_STAT: Final = ("/usr/bin/vm_stat",)
_PRESSURE_LEVEL: Final = (
    "/usr/sbin/sysctl",
    "-n",
    "kern.memorystatus_vm_pressure_level",
)
_SWAP_USAGE: Final = ("/usr/sbin/sysctl", "-n", "vm.swapusage")
_COMMAND_TIMEOUT_SEC: Final = 5.0
_MB: Final = 1 << 20

_COMPRESSOR: Final = "Pages occupied by compressor"
_COMPRESSIONS: Final = "Compressions"
_DECOMPRESSIONS: Final = "Decompressions"
_SWAPOUTS: Final = "Swapouts"
_REQUIRED_COUNTERS: Final = frozenset(
    {_COMPRESSOR, _COMPRESSIONS, _DECOMPRESSIONS, _SWAPOUTS}
)
_PAGE_SIZE: Final = re.compile(r"page size of (\d+) bytes")
# "Pages free:   7880." and the quoted form '"Translation faults":   24817916902.'
_COUNTER: Final = re.compile(r'^"?([^":\n]+)"?:\s+(\d+)\.$', re.MULTILINE)
# "total = 4096.00M  used = 2762.88M  free = 1333.12M  (encrypted)"
_SWAP_USED: Final = re.compile(r"\bused = (\d+(?:\.\d+)?)([KMGT])")
_UNIT_BYTES: Final = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40}

CommandRunner = Callable[[Sequence[str]], str]


@dataclass(frozen=True, slots=True)
class VmSnapshot:
    pressure_level: int
    page_size: int
    compressor_pages: int
    compressions: int
    decompressions: int
    swapouts: int
    swap_used_bytes: int


class VmSample(TypedDict):
    """Kernel memory readings of one interval: sizes in MiB, paging rates in MiB/s."""

    pressure: int
    compressor_mb: int
    swap_mb: int
    compress_mb_s: float
    decompress_mb_s: float
    swapout_mb_s: float


def parse_snapshot(
    vm_stat: str, pressure_level: str, swap_usage: str
) -> VmSnapshot | None:
    """A snapshot from the three command outputs; None when any reading is missing."""
    page = _PAGE_SIZE.search(vm_stat)
    swap = _SWAP_USED.search(swap_usage)
    counters = {name: int(value) for name, value in _COUNTER.findall(vm_stat)}
    if page is None or swap is None or not _REQUIRED_COUNTERS <= counters.keys():
        return None
    try:
        level = int(pressure_level.strip())
    except ValueError:
        return None
    return VmSnapshot(
        pressure_level=level,
        page_size=int(page.group(1)),
        compressor_pages=counters[_COMPRESSOR],
        compressions=counters[_COMPRESSIONS],
        decompressions=counters[_DECOMPRESSIONS],
        swapouts=counters[_SWAPOUTS],
        swap_used_bytes=int(float(swap.group(1)) * _UNIT_BYTES[swap.group(2)]),
    )


def _run(argv: Sequence[str]) -> str:
    return subprocess.run(
        argv,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_COMMAND_TIMEOUT_SEC,
        check=True,
    ).stdout


def read_vm_snapshot(*, run: CommandRunner = _run) -> VmSnapshot | None:
    """Current readings; None off macOS or when a command fails."""
    if sys.platform != "darwin":
        return None
    try:
        return parse_snapshot(run(_VM_STAT), run(_PRESSURE_LEVEL), run(_SWAP_USAGE))
    except (OSError, subprocess.SubprocessError):
        return None


def vm_sample(previous: VmSnapshot, current: VmSnapshot, dt: float) -> VmSample:
    """Levels at ``current`` and paging rates over the ``dt`` (> 0) seconds since ``previous``."""

    def per_second(before: int, after: int) -> float:
        # Kernel counters only grow; a smaller value means they restarted, not negative traffic.
        return round(max(0, after - before) * current.page_size / _MB / dt, 1)

    return VmSample(
        pressure=current.pressure_level,
        compressor_mb=current.compressor_pages * current.page_size // _MB,
        swap_mb=current.swap_used_bytes // _MB,
        compress_mb_s=per_second(previous.compressions, current.compressions),
        decompress_mb_s=per_second(previous.decompressions, current.decompressions),
        swapout_mb_s=per_second(previous.swapouts, current.swapouts),
    )
