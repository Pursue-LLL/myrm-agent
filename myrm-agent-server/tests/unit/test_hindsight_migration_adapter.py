"""Unit tests for Hindsight memory database one-click migration adapter.

Verifies dual-track parsing for memory_units (world/experience/observation)
and raw chunks, tenant bank_id preservation, and parity audit verification.
"""

from app.services.memory.imports.import_adapter_registry import (
    memory_import_adapter_status,
    memory_import_supported_sources,
)
from app.services.memory.imports.migration_adapters import HindsightMemoryAdapter
from app.services.memory.imports.migration_models import (
    MemoryTargetBucket,
    MigrationFidelityLevel,
    MigrationSourceType,
)
from app.services.memory.imports.universal_memory_migration_bridge import (
    UniversalMemoryMigrationBridge,
)


def test_hindsight_memory_units_taxonomy_mapping() -> None:
    """Test 3-tier fact classification mapping for world, experience, and observation."""
    payload: dict[str, object] = {
        "bank_id": "org_venture_alpha",
        "memory_units": [
            {
                "id": "mu_world_01",
                "content": "Python 3.13 introduces experimental free-threading support.",
                "fact_type": "world",
                "confidence": 0.95,
                "chunk_id": "chk_python_notes",
            },
            {
                "id": "mu_exp_02",
                "content": "Always specify explicit wait timeouts in async subprocess calls to prevent hangs.",
                "fact_type": "experience",
                "confidence": 0.88,
                "chunk_id": "chk_postmortem_7",
            },
            {
                "id": "mu_obs_03",
                "content": "User prefers concise GitHub markdown diff blocks without repetitive chatter.",
                "fact_type": "observation",
                "confidence": 0.70,
                "chunk_id": "chk_session_pref",
            },
        ],
    }

    items = HindsightMemoryAdapter.parse(payload)
    assert len(items) == 3

    # 1. world -> SEMANTIC
    world_item = items[0]
    assert world_item.target_bucket == MemoryTargetBucket.SEMANTIC
    assert world_item.fidelity_level == MigrationFidelityLevel.STRUCTURED_SEMANTIC
    assert world_item.source_type == MigrationSourceType.HINDSIGHT
    assert world_item.metadata["bank_id"] == "org_venture_alpha"
    assert world_item.metadata["chunk_id"] == "chk_python_notes"
    assert world_item.metadata["fact_type"] == "world"

    # 2. experience -> PROCEDURAL
    exp_item = items[1]
    assert exp_item.target_bucket == MemoryTargetBucket.PROCEDURAL
    assert exp_item.fidelity_level == MigrationFidelityLevel.PROCEDURAL_RULE
    assert exp_item.importance >= 0.85
    assert exp_item.metadata["fact_type"] == "experience"

    # 3. observation -> CONVERSATION
    obs_item = items[2]
    assert obs_item.target_bucket == MemoryTargetBucket.CONVERSATION
    assert obs_item.fidelity_level == MigrationFidelityLevel.STRUCTURED_SEMANTIC
    assert obs_item.metadata["fact_type"] == "observation"


def test_hindsight_raw_chunks_mapping() -> None:
    """Test verbatim chunk slicing preserved into conversation bucket."""
    payload: dict[str, object] = {
        "bank_id": "developer_workspace",
        "chunks": [
            {
                "id": "chunk_991",
                "text": "User: Deploy the new Docker container.\nAssistant: Executing docker run...",
                "created_at": "2026-10-06T10:00:00Z",
            }
        ],
    }

    items = HindsightMemoryAdapter.parse(payload)
    assert len(items) == 1
    chunk_item = items[0]
    assert chunk_item.target_bucket == MemoryTargetBucket.CONVERSATION
    assert chunk_item.fidelity_level == MigrationFidelityLevel.LOSSLESS_VERBATIM
    assert chunk_item.content.startswith("User: Deploy")
    assert chunk_item.metadata["bank_id"] == "developer_workspace"
    assert chunk_item.metadata["chunk_id"] == "chunk_991"


def test_hindsight_bridge_sniff_and_parity_report() -> None:
    """Test heuristic sniffing and 100% parity report generation."""
    payload: dict[str, object] = {
        "_source": "hindsight_db_dump",
        "bank_id": "bank_test",
        "memory_units": [
            {
                "id": "u1",
                "fact": "Qdrant HNSW indexing scales to millions of vectors.",
                "type": "world",
            }
        ],
        "chunks": [
            {
                "id": "c1",
                "content": "Raw context snippet for verification.",
            }
        ],
    }

    sniffed = UniversalMemoryMigrationBridge.sniff_source(payload)
    assert sniffed == MigrationSourceType.HINDSIGHT

    items, report = UniversalMemoryMigrationBridge.execute_dry_run_migration(payload)
    assert len(items) == 2
    assert report.total_source_items == 2
    assert report.mapped_semantic_count == 1
    assert report.mapped_conversation_count == 1
    assert report.fidelity_ratio == 1.0
    assert report.audit_digest.startswith("parity_")
    assert len(report.warnings) == 0


def test_hindsight_registry_readiness() -> None:
    """Ensure hindsight is recognized in supported sources and marked ready."""
    supported = memory_import_supported_sources()
    status = memory_import_adapter_status()

    assert "hindsight" in supported
    assert status.get("hindsight") == "ready"
