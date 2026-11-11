"""Summary of recorded host load: pressure percentiles, distinct peaks and who drove them.

[INPUT]
- LoadSample rows from host_load_store.read_window
- host_resource_governor load-ratio thresholds (same scale the governor acts on)

[OUTPUT]
- render_summary(samples, hours=..., peaks=...) -> str

[POS]
Answers "which role burned the CPU when the machine saturated" from recorded rows alone.
Peaks closer than ``PEAK_SEPARATION_SEC`` belong to one storm and are reported once.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from e2e_core.host_load_sampler import LoadSample
from e2e_core.host_resource_governor import CRITICAL_LOAD_RATIO, DOWNGRADE_LOAD_RATIO

PEAK_SEPARATION_SEC: Final = 600.0
_PEAK_TOP_ROLES: Final = 4
_MIN_REPORTED_CORES: Final = 0.05


def _ratio(sample: LoadSample) -> float:
    return sample["load1"] / sample["ncpu"]


def _role_cpu(sample: LoadSample, role: str) -> float:
    stat = sample["roles"].get(role)
    return stat["cpu"] if stat is not None else 0.0


def _stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def _share(count: int, total: int) -> float:
    return 100 * count / total


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
        f"  {'role (mean busy cores)':<24}{'all':>10}{'elevated':>17}",
    ]
    roles = sorted({role for sample in samples for role in sample["roles"]})
    rows = [
        (
            role,
            sum(_role_cpu(sample, role) for sample in samples) / count,
            sum(_role_cpu(sample, role) for sample in hot) / len(hot) if hot else 0.0,
        )
        for role in roles
    ]
    for role, overall, elevated in sorted(
        rows, key=lambda row: (row[2], row[1]), reverse=True
    ):
        lines.append(f"  {role:<24}{overall:10.2f}{elevated:17.2f}")
    lines.append(
        f"  {'unattributed':<24}"
        f"{sum(sample['unattributed_cores'] for sample in samples) / count:10.2f}"
        f"{sum(sample['unattributed_cores'] for sample in hot) / len(hot) if hot else 0.0:17.2f}"
    )
    lines += ["", f"Top {peaks} distinct load peaks:"]
    for sample in _distinct_peaks(samples, peaks):
        lines.append(
            f"  {_stamp(sample['ts'])}  load1 {sample['load1']:.1f} (ratio {_ratio(sample):.2f})  "
            f"idle {sample['cpu_idle']:.0f}%  free {sample['mem_avail_mb']} MB  "
            f"procs {sample['procs']} (young {sample['young']})"
        )
        lines.append(f"      {_top_roles(sample)}")
    return "\n".join(lines)
