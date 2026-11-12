"""Summary of recorded host load: pressure percentiles, distinct peaks and who drove them.

[INPUT]
- LoadSample rows from host_load_store.read_window
- host_resource_governor load-ratio thresholds (same scale the governor acts on)
- host_vm_stats.PRESSURE_WARN (kernel level from which memory counts as under pressure)

[OUTPUT]
- render_summary(samples, hours=..., peaks=...) -> str

[POS]
Answers "which role burned the CPU or held the memory when the machine saturated, and was
the kernel short of memory" from recorded rows alone. Footprint columns, the kernel memory
section and the per-peak memory lines appear only when rows carry that data, so windows of
older rows render as before.
Peaks closer than ``PEAK_SEPARATION_SEC`` belong to one storm and are reported once.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from e2e_core.host_load_sampler import LoadSample
from e2e_core.host_resource_governor import CRITICAL_LOAD_RATIO, DOWNGRADE_LOAD_RATIO
from e2e_core.host_vm_stats import PRESSURE_WARN, VmSample

PEAK_SEPARATION_SEC: Final = 600.0
_PEAK_TOP_ROLES: Final = 4
_MIN_REPORTED_CORES: Final = 0.05
_MIN_REPORTED_FOOTPRINT_MB: Final = 256
_MB_PER_GB: Final = 1024


def _ratio(sample: LoadSample) -> float:
    return sample["load1"] / sample["ncpu"]


def _role_cpu(sample: LoadSample, role: str) -> float:
    stat = sample["roles"].get(role)
    return stat["cpu"] if stat is not None else 0.0


def _role_foot_mb(sample: LoadSample, role: str) -> int:
    stat = sample["roles"].get(role)
    return stat.get("foot_mb", 0) if stat is not None else 0


def _stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def _share(count: int, total: int) -> float:
    return 100 * count / total


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _with_footprint(samples: Sequence[LoadSample]) -> list[LoadSample]:
    return [
        sample
        for sample in samples
        if any("foot_mb" in stat for stat in sample["roles"].values())
    ]


def _vm_readings(samples: Sequence[LoadSample]) -> list[VmSample]:
    return [sample["vm"] for sample in samples if "vm" in sample]


def _distinct_peaks(samples: Sequence[LoadSample], limit: int) -> list[LoadSample]:
    chosen: list[LoadSample] = []
    for sample in sorted(samples, key=lambda item: item["load1"], reverse=True):
        if all(
            abs(sample["ts"] - kept["ts"]) >= PEAK_SEPARATION_SEC for kept in chosen
        ):
            chosen.append(sample)
        if len(chosen) == limit:
            break
    return chosen


def _top_roles(sample: LoadSample) -> str:
    ranked = sorted(
        sample["roles"], key=lambda role: _role_cpu(sample, role), reverse=True
    )
    parts = [
        f"{role} {_role_cpu(sample, role):.1f}c"
        for role in ranked[:_PEAK_TOP_ROLES]
        if _role_cpu(sample, role) >= _MIN_REPORTED_CORES
    ]
    parts.append(f"unattributed {sample['unattributed_cores']:.1f}c")
    return ", ".join(parts)


def _role_table(samples: Sequence[LoadSample], hot: Sequence[LoadSample]) -> list[str]:
    tracked, tracked_hot = _with_footprint(samples), _with_footprint(hot)
    header = f"  {'role (mean busy cores)':<24}{'all':>10}{'elevated':>17}"
    if tracked:
        header += f"{'foot MB all':>14}{'foot MB elev':>14}"
    roles = sorted({role for sample in samples for role in sample["roles"]})
    rows = [
        (
            role,
            _mean([_role_cpu(sample, role) for sample in samples]),
            _mean([_role_cpu(sample, role) for sample in hot]),
            _mean([_role_foot_mb(sample, role) for sample in tracked]),
            _mean([_role_foot_mb(sample, role) for sample in tracked_hot]),
        )
        for role in roles
    ]
    lines = [header]
    for role, overall, elevated, foot, foot_elevated in sorted(
        rows, key=lambda row: (row[2], row[1]), reverse=True
    ):
        line = f"  {role:<24}{overall:10.2f}{elevated:17.2f}"
        if tracked:
            line += f"{foot:14.0f}{foot_elevated:14.0f}"
        lines.append(line)
    unattributed = (
        f"  {'unattributed':<24}"
        f"{_mean([sample['unattributed_cores'] for sample in samples]):10.2f}"
        f"{_mean([sample['unattributed_cores'] for sample in hot]):17.2f}"
    )
    lines.append(unattributed + (f"{'-':>14}{'-':>14}" if tracked else ""))
    return lines


def _kernel_section(
    samples: Sequence[LoadSample], hot: Sequence[LoadSample]
) -> list[str]:
    readings, hot_readings = _vm_readings(samples), _vm_readings(hot)
    if not readings:
        return []

    def warned(items: Sequence[VmSample]) -> int:
        return sum(1 for item in items if item["pressure"] >= PRESSURE_WARN)

    compressor = sorted(item["compressor_mb"] for item in readings)
    swap_peak_gb = max(item["swap_mb"] for item in readings) / _MB_PER_GB
    compress_peak = max(item["compress_mb_s"] for item in readings)
    decompress_peak = max(item["decompress_mb_s"] for item in readings)
    swapout_peak = max(item["swapout_mb_s"] for item in readings)
    share_hot = (
        f"{_share(warned(hot_readings), len(hot_readings)):.1f}% of the elevated-load ones"
        if hot_readings
        else "no elevated-load samples"
    )
    return [
        "",
        f"Kernel memory pressure ({len(readings)} of {len(samples)} samples carry it):",
        (
            f"  level >= {PRESSURE_WARN} (warn): "
            f"{_share(warned(readings), len(readings)):.1f}% of samples, {share_hot}"
        ),
        (
            f"  compressor GB: p50 {compressor[len(compressor) // 2] / _MB_PER_GB:.1f}  "
            f"max {compressor[-1] / _MB_PER_GB:.1f}   swap GB: max {swap_peak_gb:.1f}"
        ),
        (
            f"  paging MB/s (max): compress {compress_peak:.0f}  "
            f"decompress {decompress_peak:.0f}  swap-out {swapout_peak:.0f}"
        ),
    ]


def _peak_memory_lines(sample: LoadSample) -> list[str]:
    lines: list[str] = []
    ranked = sorted(
        sample["roles"], key=lambda role: _role_foot_mb(sample, role), reverse=True
    )
    holders = [
        f"{role} {_role_foot_mb(sample, role) / _MB_PER_GB:.1f} GB"
        for role in ranked[:_PEAK_TOP_ROLES]
        if _role_foot_mb(sample, role) >= _MIN_REPORTED_FOOTPRINT_MB
    ]
    if holders:
        lines.append("footprint: " + ", ".join(holders))
    if "vm" in sample:
        vm = sample["vm"]
        lines.append(
            f"kernel: level {vm['pressure']}, compressor "
            f"{vm['compressor_mb'] / _MB_PER_GB:.1f} GB, swap "
            f"{vm['swap_mb'] / _MB_PER_GB:.1f} GB, decompress "
            f"{vm['decompress_mb_s']:.0f} MB/s"
        )
    return lines


def render_summary(samples: Sequence[LoadSample], *, hours: float, peaks: int) -> str:
    if not samples:
        return f"No samples in the last {hours:g}h (is the recorder running? see `status`)."
    count = len(samples)
    ratios = sorted(_ratio(sample) for sample in samples)
    hot = [sample for sample in samples if _ratio(sample) >= DOWNGRADE_LOAD_RATIO]
    critical = sum(1 for ratio in ratios if ratio >= CRITICAL_LOAD_RATIO)
    coverage = min(
        100.0, 100 * sum(sample["dt"] for sample in samples) / (hours * 3600)
    )
    p50 = ratios[count // 2]
    p95 = ratios[min(count - 1, int(0.95 * count))]
    lines = [
        f"Window {hours:g}h: {count} samples, coverage {coverage:.0f}%",
        f"Load ratio (load1 / cores): p50 {p50:.2f}  p95 {p95:.2f}  max {ratios[-1]:.2f}",
        (
            f"Samples at/above {DOWNGRADE_LOAD_RATIO:g}: {_share(len(hot), count):.1f}%   "
            f"at/above {CRITICAL_LOAD_RATIO:g}: {_share(critical, count):.1f}%"
        ),
        "",
        *_role_table(samples, hot),
        *_kernel_section(samples, hot),
        "",
        f"Top {peaks} distinct load peaks:",
    ]
    for sample in _distinct_peaks(samples, peaks):
        lines.append(
            f"  {_stamp(sample['ts'])}  load1 {sample['load1']:.1f} (ratio {_ratio(sample):.2f})  "
            f"idle {sample['cpu_idle']:.0f}%  free {sample['mem_avail_mb']} MB  "
            f"procs {sample['procs']} (young {sample['young']})"
        )
        lines.append(f"      {_top_roles(sample)}")
        lines.extend(f"      {line}" for line in _peak_memory_lines(sample))
    return "\n".join(lines)
