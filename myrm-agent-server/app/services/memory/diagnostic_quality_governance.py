"""Memory quality governance diagnostic probe.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: protocol-first memory runtime)

[OUTPUT]
run_memory_quality_probe: content-safe quality governance probe for Memory Doctor.

[POS]
单用户记忆质量治理探针。读取框架层健康评分，不读取业务记忆内容到诊断 evidence。
"""

from __future__ import annotations

from time import perf_counter

from myrm_agent_harness.toolkits.memory import MemoryManager

from app.schemas.memory.command_center import MemoryCommandDiagnosticProbeResult
from app.services.memory.diagnostic_probe_results import critical_probe, missing_probe

DiagnosticStatus = str


async def run_memory_quality_probe(manager: MemoryManager | None) -> MemoryCommandDiagnosticProbeResult:
    """Compute content-safe memory quality governance evidence."""

    started = perf_counter()
    if manager is None:
        return missing_probe(
            probe_id="memory_quality_governance",
            category="quality",
            label="Memory quality governance",
            started=started,
            evidence="Memory manager dependency was not available to diagnostics.",
            impact="Freshness, coverage, retention, and coherence quality cannot be assessed.",
            next_action="Open the memory command center through the normal GUI runtime and rerun diagnostics.",
        )
    try:
        health = await manager.compute_health_score()
    except Exception as exc:
        return critical_probe(
            probe_id="memory_quality_governance",
            category="quality",
            label="Memory quality governance",
            started=started,
            evidence=f"Memory quality probe failed: {type(exc).__name__}.",
            impact="The product cannot distinguish healthy persistent memory from stale or low-coverage memory.",
            next_action="Refresh the health snapshot and review storage/index configuration.",
            repair_actions=["run_health_refresh", "review_storage_config"],
        )
    if health.total >= 80:
        status: DiagnosticStatus = "ready"
    elif health.total >= 60:
        status = "warning"
    else:
        status = "critical"
    return MemoryCommandDiagnosticProbeResult(
        id="memory_quality_governance",
        category="quality",
        label="Memory quality governance",
        status=status,
        evidence=(
            f"Health score={health.total}; dimensions={len(health.dimensions)}; "
            f"suggestions={len(health.suggestions)}; sample_size={health.sample_size}."
        ),
        impact="Memory quality governance keeps long-term memory useful instead of only accumulating records.",
        next_action="No action required." if status == "ready" else "Review health suggestions and refresh the health snapshot.",
        safe_to_retry=True,
        duration_ms=round((perf_counter() - started) * 1000, 2),
        repair_actions=[] if status == "ready" else ["run_health_refresh"],
    )
