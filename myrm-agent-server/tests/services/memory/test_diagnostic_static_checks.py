"""Unit tests for static Memory Doctor checks.

[INPUT]
app.schemas.memory.command_center::MemoryCommandRuntimeStatus (POS: deployment and storage status)
app.services.memory.diagnostic_static_checks (POS: static doctor check builders)

[OUTPUT]
Coverage for persistence-aware probe_vector_index and relational probe defaults.
"""

from app.schemas.memory.command_center import MemoryCommandRuntimeStatus
from app.services.memory.diagnostic_static_checks import (
    probe_relational_store,
    probe_vector_index,
)


def _runtime(
    *,
    vector_status: str = "available",
    vector_persistence: str = "persistent",
    relational_status: str = "unavailable",
) -> MemoryCommandRuntimeStatus:
    return MemoryCommandRuntimeStatus(
        deploy_mode="local",
        storage_mode="local",
        memory_base_path="/tmp/memory",
        relational_status=relational_status,
        vector_status=vector_status,
        vector_persistence=vector_persistence,
        graph_status="unavailable",
        embedding_status="custom",
        control_plane_status="not_used",
        event_ledger_status="available",
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
    assert "lost on restart" in check.impact
    assert check.repair_actions == ["review_storage_config", "run_diagnostics"]


def test_probe_vector_index_missing_without_store() -> None:
    check = probe_vector_index(_runtime(vector_status="unavailable", vector_persistence="unavailable"))
    assert check.status == "missing"
    assert check.repair_actions == ["enable_vector_store", "configure_embedding"]


def test_probe_relational_store_defaults() -> None:
    check = probe_relational_store(_runtime())
    assert check.status == "critical"
