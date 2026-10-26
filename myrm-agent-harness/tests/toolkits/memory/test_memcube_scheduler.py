"""Comprehensive test suite for Unified MemCube Envelope and Multi-Tier Scheduler.

Validates:
1. Static contract & zero-overhead envelope sealing.
2. Canonical SHA256 audit hash generation and tamper detection.
3. Full coverage across all 7 memory entity kinds.
4. Policy-based storage dispatch (relational and vector through the manager, graph undispatched).
5. Anti-tamper gate in import_envelopes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.cube import (
    LifecycleTier,
    MemCubeEnvelope,
    StoragePolicy,
    infer_tier_and_policy,
    unwrap_envelope,
    wrap_into_envelope,
)
from myrm_agent_harness.toolkits.memory.scheduler import MultiTierMemoryScheduler
from myrm_agent_harness.toolkits.memory.types import (
    ClaimMemory,
    ConversationMemory,
    EpisodicMemory,
    IntegrationMemory,
    MemoryScope,
    MemoryType,
    ProceduralMemory,
    SemanticMemory,
    TaskDigestMemory,
)


def _make_sample_memories() -> list[object]:
    """Generate sample instances for all 7 memory types."""
    now = datetime.now(UTC)
    scope = MemoryScope()

    return [
        SemanticMemory(
            id="sem-1",
            content="Agent prefers python 3.12 syntax",
            scope=scope,
            created_at=now,
            updated_at=now,
        ),
        EpisodicMemory(
            id="epi-1",
            content="Completed data migration smoothly",
            scope=scope,
            created_at=now,
            updated_at=now,
        ),
        ProceduralMemory(
            id="proc-1",
            content="Always run tests before committing",
            trigger="before git commit",
            action="run pytest and ruff",
            scope=scope,
            created_at=now,
            updated_at=now,
        ),
        ConversationMemory(
            id="conv-1",
            content="User said: start task",
            raw_exchange="User: start task\nAssistant: sure",
            session_id="sess-100",
            created_at=now,
            updated_at=now,
        ),
        ClaimMemory(
            id="claim-1",
            subject="System",
            predicate="operates_on",
            object_val="Darwin",
            claim_key="sys-os-darwin",
            title="OS platform",
            claim_text="System operates on Darwin",
            content="System operates on Darwin",
            scope=scope,
            created_at=now,
            updated_at=now,
        ),
        IntegrationMemory(
            id="integ-1",
            provider="github",
            source_platform="github",
            external_id="gh-issue-42",
            content="Fix null pointer exception",
            scope=scope,
            created_at=now,
            updated_at=now,
        ),
        TaskDigestMemory(
            id="digest-1",
            task_goal="Refactor Memory Store",
            source_session_id="sess-200",
            status="completed",
            created_at=now,
            updated_at=now,
        ),
    ]


def test_cube_envelope_seal_and_verify() -> None:
    """Test standard envelope creation, audit hashing, and verification."""
    sem = SemanticMemory(
        id="sem-test",
        content="Testing audit hash integrity",
    )
    env = wrap_into_envelope(sem)

    assert env.header.memory_type == MemoryType.SEMANTIC
    assert env.header.lifecycle_tier == LifecycleTier.L3_COMPILED
    assert env.header.storage_policy == StoragePolicy.VECTOR
    assert env.header.audit_hash is not None
    assert env.verify_audit_hash() is True

    # Unwrap test
    unwrapped = unwrap_envelope(env)
    assert isinstance(unwrapped, SemanticMemory)
    assert unwrapped.id == sem.id
    assert unwrapped.content == sem.content


def test_cube_envelope_tamper_detection() -> None:
    """Tampering with header or payload invalidates audit hash."""
    proc = ProceduralMemory(
        id="rule-1",
        content="Never delete db",
        trigger="on database clear",
        action="require user confirmation",
    )
    env = wrap_into_envelope(proc)
    assert env.verify_audit_hash() is True

    # Tamper payload content
    tampered_env = MemCubeEnvelope[dict[str, object]](
        header=env.header,
        payload={"id": "rule-1", "content": "Always delete db"},
    )
    assert tampered_env.verify_audit_hash() is False

    # Tamper header attribute
    tampered_header = env.header.model_copy(update={"priority": 5})
    tampered_env2 = MemCubeEnvelope[dict[str, object]](
        header=tampered_header,
        payload=dict(env.payload),
    )
    assert tampered_env2.verify_audit_hash() is False


def test_infer_tier_and_policy_all_seven_types() -> None:
    """Verify tier and policy inference for all 7 memory types."""
    samples = _make_sample_memories()
    assert len(samples) == 7

    for item in samples:
        tier, policy = infer_tier_and_policy(item)
        assert isinstance(tier, LifecycleTier)
        assert isinstance(policy, StoragePolicy)

        # Wrap item and check round-trip
        env = wrap_into_envelope(item)
        assert env.header.lifecycle_tier == tier
        assert env.header.storage_policy == policy
        assert env.verify_audit_hash() is True


@pytest.mark.asyncio
async def test_scheduler_dispatch_routes() -> None:
    """Relational and vector memories are written through the manager; graph has no write target."""
    mock_manager = AsyncMock()
    mock_manager.store = AsyncMock()
    scheduler = MultiTierMemoryScheduler(memory_manager=mock_manager)

    # 1. TaskDigest -> RELATIONAL policy -> manager.store
    digest = TaskDigestMemory(id="td-1", task_goal="Optimize DB", source_session_id="s1")
    assert await scheduler.dispatch_store(digest) is True
    mock_manager.store.assert_awaited_with(digest)

    # 2. Semantic -> VECTOR policy -> manager.store
    sem = SemanticMemory(id="sem-1", content="test")
    assert await scheduler.dispatch_store(sem) is True
    mock_manager.store.assert_awaited_with(sem)
    assert mock_manager.store.await_count == 2

    # 3. Claim -> GRAPH policy has no write target and must not reach the manager
    claim = ClaimMemory(
        id="c-1",
        subject="A",
        predicate="B",
        object_val="C",
        claim_key="k1",
        title="T1",
        claim_text="Text 1",
        content="Text 1",
    )
    assert await scheduler.dispatch_store(claim) is False
    assert mock_manager.store.await_count == 2


@pytest.mark.asyncio
async def test_scheduler_dispatch_skips_ephemeral_and_reports_write_failures() -> None:
    """Ephemeral memories are never persisted; a rejected write is reported, not raised."""
    mock_manager = AsyncMock()
    scheduler = MultiTierMemoryScheduler(memory_manager=mock_manager)
    sem = SemanticMemory(id="sem-2", content="scratch")

    assert await scheduler.dispatch_store(sem, policy=StoragePolicy.EPHEMERAL) is True
    mock_manager.store.assert_not_awaited()

    mock_manager.store.side_effect = ValueError("Unknown memory type")
    assert await scheduler.dispatch_store(sem) is False
    assert await MultiTierMemoryScheduler().dispatch_store(sem) is False


@pytest.mark.asyncio
async def test_scheduler_import_envelopes_anti_tamper() -> None:
    """Scheduler rejects tampered envelopes when verify_hashes=True."""
    mock_manager = AsyncMock()
    scheduler = MultiTierMemoryScheduler(memory_manager=mock_manager)

    proc = ProceduralMemory(id="p1", content="Safe rule", trigger="t1", action="a1")
    env = wrap_into_envelope(proc)
    env_dict = env.model_dump(mode="json")

    # Tamper payload
    env_dict["payload"]["content"] = "Tampered malicious rule"

    with pytest.raises(ValueError, match="Tamper detected"):
        await scheduler.import_envelopes([env_dict], verify_hashes=True)
    mock_manager.store.assert_not_awaited()

    # When verify_hashes=False, import proceeds
    restored, skipped = await scheduler.import_envelopes([env_dict], verify_hashes=False)
    assert restored == 1
    assert skipped == 0
    assert mock_manager.store.await_count == 1


def test_memcube_access_count_and_timestamp_roundtrip() -> None:
    """Validate that access_count and last_accessed_at survive MemCube sealing and unwrap without data loss."""
    accessed_time = datetime(2026, 9, 17, 12, 30, 0, tzinfo=UTC)
    sem = SemanticMemory(
        id="sem-usage-test",
        content="Frequent user preference",
        access_count=77,
        last_accessed_at=accessed_time,
    )

    env = wrap_into_envelope(sem)
    assert env.header.usage_count == 77
    assert env.header.last_accessed_at == accessed_time
    assert env.verify_audit_hash() is True

    unwrapped = unwrap_envelope(env)
    assert isinstance(unwrapped, SemanticMemory)
    assert unwrapped.id == "sem-usage-test"
    assert unwrapped.access_count == 77
    assert unwrapped.last_accessed_at == accessed_time
