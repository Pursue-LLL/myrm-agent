"""Startup budget contract: what one cold backend start may cost, and how to judge a sample.

[INPUT]
  Sample values from probe.py; MYRM_STARTUP_BUDGET_CPU_SCALE (float, default 1.0)

[OUTPUT]
  Sample / Budget / Finding, BUDGET, best() / evaluate() / render()

[POS]
  Pure policy (no I/O) so the limits and the judging rule are unit-testable. Calibrated on
  2026-10-31 on a heavily loaded 12-core Mac (load 25-77), source run, isolated empty database.
  Two kinds of limit, deliberately different:
    * modules is deterministic for a given lockfile. It is the sharp limit: an eager import of a
      heavy package shows up as hundreds of modules, regardless of how busy the machine is.
    * CPU seconds are a coarse backstop with wide headroom. Contention alone moved the same
      ``import app.main`` between 6.2 and 9.9 s CPU, so only a gross regression may trip them.
  Raising a limit is a deliberate act: change BUDGET in the same commit that adds the cost.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

CPU_SCALE_ENV = "MYRM_STARTUP_BUDGET_CPU_SCALE"


@dataclass(frozen=True)
class Sample:
    import_cpu_sec: float
    modules: int
    peak_rss_mb: float
    # None for an import-only (stubbed) measurement.
    gateway_cpu_sec: float | None


@dataclass(frozen=True)
class Budget:
    import_cpu_sec: float
    modules: int
    gateway_cpu_sec: float


@dataclass(frozen=True)
class Finding:
    metric: str
    observed: float
    limit: float

    def render(self) -> str:
        return f"{self.metric}: {self.observed:g} > limit {self.limit:g}"


# Measured: import_cpu 5.5-6.9 s (9.9 s at the worst contention seen), modules 8226 on every
# run, gateway_cpu 0.30-0.51 s. Limits: import CPU 1.7x the slowest best sample seen, +5%
# modules (a heavy eager import adds hundreds), gateway CPU ~3x the slowest.
BUDGET = Budget(import_cpu_sec=12.0, modules=8650, gateway_cpu_sec=1.5)


def best(samples: list[Sample]) -> Sample:
    """Per-metric minimum: contention only ever inflates a measurement, never shrinks it."""
    if not samples:
        raise ValueError("at least one sample is required")
    gateway = [s.gateway_cpu_sec for s in samples if s.gateway_cpu_sec is not None]
    return Sample(
        import_cpu_sec=min(s.import_cpu_sec for s in samples),
        modules=min(s.modules for s in samples),
        peak_rss_mb=min(s.peak_rss_mb for s in samples),
        gateway_cpu_sec=min(gateway) if gateway else None,
    )


def cpu_scale() -> float:
    """CPU limits scale with the machine; the module limit does not."""
    raw = os.environ.get(CPU_SCALE_ENV)
    if raw is None:
        return 1.0
    try:
        scale = float(raw)
    except ValueError as exc:
        raise ValueError(f"{CPU_SCALE_ENV} must be a number, got {raw!r}") from exc
    if scale <= 0:
        raise ValueError(f"{CPU_SCALE_ENV} must be positive, got {raw!r}")
    return scale


def evaluate(sample: Sample, budget: Budget = BUDGET) -> list[Finding]:
    """Every limit the sample exceeds (empty list = within budget)."""
    scale = cpu_scale()
    checks: list[tuple[str, float | None, float]] = [
        ("import_cpu_sec", sample.import_cpu_sec, budget.import_cpu_sec * scale),
        ("modules", float(sample.modules), float(budget.modules)),
        ("gateway_cpu_sec", sample.gateway_cpu_sec, budget.gateway_cpu_sec * scale),
    ]
    return [
        Finding(metric, observed, limit)
        for metric, observed, limit in checks
        if observed is not None and observed > limit
    ]


def render(sample: Sample, budget: Budget = BUDGET) -> str:
    scale = cpu_scale()
    gateway = (
        "n/a" if sample.gateway_cpu_sec is None else f"{sample.gateway_cpu_sec:g}s"
    )
    return (
        f"STARTUP_BUDGET import_cpu={sample.import_cpu_sec:g}s"
        f"/{budget.import_cpu_sec * scale:g}s modules={sample.modules}/{budget.modules}"
        f" gateway_cpu={gateway}/{budget.gateway_cpu_sec * scale:g}s"
        f" peak_rss={sample.peak_rss_mb:g}MB"
    )
