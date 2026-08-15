"""Memory Doctor diagnostic domain: probes, benchmark, repair plans, SLO.

[INPUT]
- MemoryManager / MemoryOperationLedgerService handles from the memory service.
- MemoryCommandRuntimeStatus snapshot of the runtime surface.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``diagnostic``
  subpackage, consumed by the ``diagnostics.py`` orchestrator facade:
  - diagnostic_probe_results: probe rollup/status helpers + critical/missing probe
  - diagnostic_quality_governance: run_memory_quality_probe
  - diagnostic_recall_benchmark: run_golden_recall_benchmark
  - diagnostic_repair_plans: build_repair_plans / with_check_repair_plans /
    with_probe_repair_plans
  - diagnostic_repair_executor: MemoryDiagnosticRepairExecutor
  - diagnostic_slo: build_diagnostic_slo
  - diagnostic_static_checks: static runtime-surface probes (relational store,
    memory base path, vector index, knowledge graph, embedding provider, ...)

[POS]
Server business layer. Single Memory Doctor diagnostic domain: every
``diagnostic_*`` module is orchestrated by ``diagnostics.py`` and shares probe
primitives, so the seven modules stay co-located under one facade.
"""

from app.services.memory.diagnostics.diagnostic.diagnostic_probe_results import (
    critical_probe,
    doctor_check_to_probe,
    missing_probe,
    operation_status,
    rollup_status,
    run_summary,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_quality_governance import (
    run_memory_quality_probe,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_recall_benchmark import (
    run_golden_recall_benchmark,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_repair_executor import (
    MemoryDiagnosticRepairExecutor,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_repair_plans import (
    build_repair_plans,
    with_check_repair_plans,
    with_probe_repair_plans,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_slo import build_diagnostic_slo
from app.services.memory.diagnostics.diagnostic.diagnostic_static_checks import (
    probe_context_bundle_manifest,
    probe_deployment_boundary,
    probe_embedding_provider,
    probe_event_ledger_snapshot,
    probe_health_snapshot,
    probe_knowledge_graph,
    probe_memory_base_path,
    probe_relational_store,
    probe_vector_index,
)

__all__ = [
    "MemoryDiagnosticRepairExecutor",
    "build_diagnostic_slo",
    "build_repair_plans",
    "critical_probe",
    "doctor_check_to_probe",
    "missing_probe",
    "operation_status",
    "probe_context_bundle_manifest",
    "probe_deployment_boundary",
    "probe_embedding_provider",
    "probe_event_ledger_snapshot",
    "probe_health_snapshot",
    "probe_knowledge_graph",
    "probe_memory_base_path",
    "probe_relational_store",
    "probe_vector_index",
    "rollup_status",
    "run_golden_recall_benchmark",
    "run_memory_quality_probe",
    "run_summary",
    "with_check_repair_plans",
    "with_probe_repair_plans",
]
