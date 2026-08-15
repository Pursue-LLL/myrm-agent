"""Unit tests for static Memory Doctor checks.

[INPUT]
app.schemas.memory.command_center::MemoryCommandRuntimeStatus (POS: deployment and storage status)
app.services.memory.diagnostics.diagnostic_static_checks (POS: static doctor check builders)

[OUTPUT]
Coverage for all static doctor probes, including persistence-aware probe_vector_index.
"""

from unittest.mock import patch

from app.schemas.memory.command_center import MemoryCommandRuntimeStatus
from app.services.memory.diagnostics.diagnostic_static_checks import (
    probe_context_bundle_manifest,
    probe_deployment_boundary,
    probe_embedding_provider,
    probe_event_ledger_snapshot,
    probe_health_snapshot,
    probe_knowledge_graph,
    probe_memory_base_path,
    probe_orphan_collections,
    probe_relational_store,
    probe_vector_index,
)


def _runtime(
    *,
    vector_status: str = "available",
    vector_persistence: str = "persistent",
    relational_status: str = "unavailable",
    graph_status: str = "unavailable",
    embedding_status: str = "custom",
    event_ledger_status: str = "available",
    control_plane_status: str = "not_used",
) -> MemoryCommandRuntimeStatus:
    return MemoryCommandRuntimeStatus(
        deploy_mode="local",
        storage_mode="local",
        memory_base_path="/tmp/memory",
        relational_status=relational_status,
        vector_status=vector_status,
        vector_persistence=vector_persistence,
        graph_status=graph_status,
        embedding_status=embedding_status,
        control_plane_status=control_plane_status,
        event_ledger_status=event_ledger_status,
        health_snapshot_status="available",
        supported_clients=["local_web"],
    )


def test_probe_vector_index_ready_when_persistent() -> None:
    check = probe_vector_index(_runtime())
    assert check.status == "ready"
    assert check.repair_actions == []


def test_probe_vector_index_warns_on_memory_fallback() -> None:
    """fallback 到内存模式的 store 必须 warning，且明确告知重启丢失。"""
    check = probe_vector_index(_runtime(vector_persistence="memory_fallback"))
    assert check.status == "warning"
    assert "degraded to an in-memory instance" in check.evidence
    assert "lost on restart" in check.impact
    assert check.repair_actions == ["review_storage_config", "run_diagnostics"]


def test_probe_vector_index_missing_without_store() -> None:
    check = probe_vector_index(_runtime(vector_status="unavailable", vector_persistence="unavailable"))
    assert check.status == "missing"
    assert check.repair_actions == ["enable_vector_store", "configure_embedding"]


def test_probe_relational_store_defaults() -> None:
    check = probe_relational_store(_runtime())
    assert check.status == "critical"
    assert check.repair_actions == ["review_storage_config"]


def test_probe_relational_store_ready() -> None:
    check = probe_relational_store(_runtime(relational_status="available"))
    assert check.status == "ready"
    assert check.repair_actions == []


def test_probe_memory_base_path_writable(tmp_path) -> None:
    runtime = _runtime()
    runtime.memory_base_path = str(tmp_path)
    check = probe_memory_base_path(runtime)
    assert check.status == "ready"


def test_probe_memory_base_path_not_writable() -> None:
    check = probe_memory_base_path(_runtime())
    assert check.status in {"ready", "critical"}


def test_probe_knowledge_graph_ready() -> None:
    check = probe_knowledge_graph(_runtime(graph_status="available"))
    assert check.status == "ready"
    assert check.repair_actions == []


def test_probe_knowledge_graph_warning() -> None:
    check = probe_knowledge_graph(_runtime(graph_status="unavailable"))
    assert check.status == "warning"
    assert check.repair_actions == ["review_storage_config"]


def test_probe_embedding_provider_ready() -> None:
    check = probe_embedding_provider(_runtime())
    assert check.status == "ready"
    assert check.repair_actions == []


def test_probe_embedding_provider_critical() -> None:
    check = probe_embedding_provider(_runtime(embedding_status="unavailable"))
    assert check.status == "critical"
    assert check.repair_actions == ["configure_embedding"]


def test_probe_event_ledger_snapshot_ready() -> None:
    check = probe_event_ledger_snapshot(_runtime())
    assert check.status == "ready"


def test_probe_event_ledger_snapshot_critical() -> None:
    check = probe_event_ledger_snapshot(_runtime(event_ledger_status="unavailable"))
    assert check.status == "critical"
    assert check.repair_actions == ["review_storage_config"]


def test_probe_health_snapshot_ready() -> None:
    check = probe_health_snapshot("fresh")
    assert check.status == "ready"
    assert check.can_auto_fix is False


def test_probe_health_snapshot_stale() -> None:
    check = probe_health_snapshot("stale")
    assert check.status == "warning"
    assert check.can_auto_fix is True
    assert check.repair_actions == ["run_health_refresh"]


def test_probe_deployment_boundary() -> None:
    check = probe_deployment_boundary(_runtime())
    assert check.status == "ready"
    assert "local_web" in check.evidence
    assert "control plane status: not_used" in check.evidence


def test_probe_orphan_collections_with_orphans() -> None:
    check = probe_orphan_collections(orphan_count=2, old_models=["model-a", "model-b"])
    assert check.status == "warning"
    assert check.repair_actions == ["reindex_memories"]


def test_probe_orphan_collections_clean() -> None:
    check = probe_orphan_collections(orphan_count=0, old_models=[])
    assert check.status == "ready"
    assert check.repair_actions == []


def test_probe_context_bundle_manifest_ready(tmp_path) -> None:
    with patch(
        "myrm_agent_harness.toolkits.context_bundle.run_migration_dry_run",
        return_value=_FakeDryRunReport(ok=True, manifest_exists=True, writable=True, actions=[]),
    ):
        check = probe_context_bundle_manifest(_runtime())
    assert check.status == "ready"


def test_probe_context_bundle_manifest_missing(tmp_path) -> None:
    with patch(
        "myrm_agent_harness.toolkits.context_bundle.run_migration_dry_run",
        return_value=_FakeDryRunReport(ok=True, manifest_exists=False, writable=True, actions=[]),
    ):
        check = probe_context_bundle_manifest(_runtime())
    assert check.status == "warning"
    assert check.repair_actions == ["review_storage_config"]


def test_probe_context_bundle_manifest_not_writable(tmp_path) -> None:
    with patch(
        "myrm_agent_harness.toolkits.context_bundle.run_migration_dry_run",
        return_value=_FakeDryRunReport(ok=True, manifest_exists=True, writable=False, actions=[]),
    ):
        check = probe_context_bundle_manifest(_runtime())
    assert check.status == "critical"


class _FakeDryRunReport:
    def __init__(self, *, ok: bool, manifest_exists: bool, writable: bool, actions: list[str]) -> None:
        self.ok = ok
        self.manifest_exists = manifest_exists
        self.writable = writable
        self.actions = actions
