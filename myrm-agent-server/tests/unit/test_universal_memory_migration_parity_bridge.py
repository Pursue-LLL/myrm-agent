from __future__ import annotations

from app.services.memory.migration.adapters import (
    LangChainMemoryAdapter,
    LettaMemGPTMigrationAdapter,
    Mem0MigrationAdapter,
    OpenClawMigrationAdapter,
    ZepMigrationAdapter,
)
from app.services.memory.migration.bridge import UniversalMemoryMigrationBridge
from app.services.memory.migration.models import (
    MemoryTargetBucket,
    MigrationFidelityLevel,
    MigrationSourceType,
)


def test_sniff_source_detection() -> None:
    bridge = UniversalMemoryMigrationBridge()

    # Mem0
    assert (
        bridge.sniff_source({"memories": [{"memory": "User likes Python"}]})
        == MigrationSourceType.MEM0
    )
    # Letta (MemGPT)
    assert (
        bridge.sniff_source({"persona": "I am a helpful assistant", "human": "User is a coder"})
        == MigrationSourceType.LETTA_MEMGPT
    )
    # LangChain
    assert (
        bridge.sniff_source({"entities": {"Python": "Language"}})
        == MigrationSourceType.LANGCHAIN
    )
    # OpenClaw
    assert (
        bridge.sniff_source({"preferences": {"theme": "dark"}, "sessions": []})
        == MigrationSourceType.OPENCLAW
    )
    # Zep
    assert (
        bridge.sniff_source({"facts": ["User lives in SF"]})
        == MigrationSourceType.ZEP
    )
    # Unknown
    assert (
        bridge.sniff_source({"random_field": 123})
        == MigrationSourceType.UNKNOWN
    )


def test_mem0_migration_parsing() -> None:
    raw_payload: dict[str, object] = {
        "memories": [
            {
                "id": "mem_001",
                "memory": "User prefers dark mode and concise answers",
                "metadata": {"importance": 0.85, "tags": ["preference", "ui"]},
                "user_id": "usr_999",
                "hash": "abc123hash",
                "created_at": "2026-09-01T12:00:00Z",
            },
            {
                "id": "mem_002",
                "text": "User backend stack is FastAPI + PostgreSQL",
                "metadata": {"importance": 0.9},
            },
        ]
    }

    items = Mem0MigrationAdapter.parse(raw_payload)
    assert len(items) == 2
    assert items[0].source_type == MigrationSourceType.MEM0
    assert items[0].target_bucket == MemoryTargetBucket.SEMANTIC
    assert items[0].fidelity_level == MigrationFidelityLevel.STRUCTURED_SEMANTIC
    assert items[0].importance == 0.85
    assert "preference" in items[0].tags
    assert items[0].metadata.get("user_id") == "usr_999"

    assert items[1].content == "User backend stack is FastAPI + PostgreSQL"
    assert items[1].importance == 0.9


def test_letta_memgpt_dual_track_migration() -> None:
    raw_payload: dict[str, object] = {
        "persona": "You are Myrm Agent, strict and high performance.",
        "human": "User is Lead Architect pursuing zero technical debt.",
        "archival_passages": [
            {
                "id": "pass_101",
                "text": "Project architecture follows sandbox isolation strategy.",
                "tags": ["arch", "sandbox"],
                "created_at": "2026-09-01T10:00:00Z",
            }
        ],
        "messages": [
            {
                "id": "msg_001",
                "role": "user",
                "text": "Hello, let's start refactoring.",
            },
            {
                "id": "msg_002",
                "role": "assistant",
                "text": "Ready. Let's inspect the files first.",
            },
        ],
    }

    items = LettaMemGPTMigrationAdapter.parse(raw_payload)
    assert len(items) == 5

    # Core Persona -> PROCEDURAL
    persona_item = next(it for it in items if it.source_id == "core_persona")
    assert persona_item.target_bucket == MemoryTargetBucket.PROCEDURAL
    assert persona_item.fidelity_level == MigrationFidelityLevel.PROCEDURAL_RULE
    assert persona_item.importance == 0.9

    # Core Human -> SEMANTIC
    human_item = next(it for it in items if it.source_id == "core_human")
    assert human_item.target_bucket == MemoryTargetBucket.SEMANTIC
    assert human_item.importance == 0.9

    # Archival Passages -> SEMANTIC
    archival_item = next(it for it in items if it.source_id == "pass_101")
    assert archival_item.target_bucket == MemoryTargetBucket.SEMANTIC
    assert "sandbox" in archival_item.tags

    # Messages -> CONVERSATION
    conv_items = [it for it in items if it.target_bucket == MemoryTargetBucket.CONVERSATION]
    assert len(conv_items) == 2
    assert conv_items[0].fidelity_level == MigrationFidelityLevel.LOSSLESS_VERBATIM


def test_langchain_migration_parsing() -> None:
    raw_payload: dict[str, object] = {
        "chat_history": [
            {"type": "human", "content": "How does vector search work?"},
            {"type": "ai", "content": "It computes cosine similarity on embeddings."},
        ],
        "entities": {
            "Qdrant": "Vector database used for persistent semantic recall",
            "Sqlite": "Relational storage for conversation ledger",
        },
    }

    items = LangChainMemoryAdapter.parse(raw_payload)
    assert len(items) == 4

    conv_items = [it for it in items if it.target_bucket == MemoryTargetBucket.CONVERSATION]
    sem_items = [it for it in items if it.target_bucket == MemoryTargetBucket.SEMANTIC]

    assert len(conv_items) == 2
    assert len(sem_items) == 2
    assert any("Qdrant" in it.content for it in sem_items)


def test_openclaw_and_zep_migration_parsing() -> None:
    openclaw_payload: dict[str, object] = {
        "preferences": {"default_editor": "cursor"},
        "sessions": [{"id": "s1", "transcript": "User: hi\nAssistant: hello"}],
    }
    openclaw_items = OpenClawMigrationAdapter.parse(openclaw_payload)
    assert len(openclaw_items) == 2
    assert openclaw_items[0].target_bucket == MemoryTargetBucket.SEMANTIC
    assert openclaw_items[1].target_bucket == MemoryTargetBucket.CONVERSATION

    zep_payload: dict[str, object] = {
        "facts": [{"fact": "User is deploying on Cloudflare Workers"}]
    }
    zep_items = ZepMigrationAdapter.parse(zep_payload)
    assert len(zep_items) == 1
    assert zep_items[0].target_bucket == MemoryTargetBucket.SEMANTIC
    assert "Cloudflare" in zep_items[0].content


def test_universal_bridge_dry_run_and_parity_report() -> None:
    bridge = UniversalMemoryMigrationBridge()

    payload: dict[str, object] = {
        "_source": "letta",
        "persona": "Assistant Persona",
        "human": "Developer Profile",
        "archival_passages": [{"id": "p1", "text": "Passage text"}],
    }

    items, report = bridge.execute_dry_run_migration(payload)

    assert len(items) == 3
    assert report.source_type == MigrationSourceType.LETTA_MEMGPT
    assert report.total_source_items == 3
    assert report.mapped_procedural_count == 1
    assert report.mapped_semantic_count == 2
    assert report.dropped_or_invalid_count == 0
    assert report.fidelity_ratio == 1.0
    assert report.audit_digest.startswith("parity_")
    assert not report.warnings
