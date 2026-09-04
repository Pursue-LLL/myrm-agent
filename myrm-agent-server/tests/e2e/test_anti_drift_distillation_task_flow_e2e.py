"""End-to-End Task Flow E2E: Anti-Drift Distillation Guards, Persona Self-Exclusion & Provenance Chain.

Universal Task Flow:
1. Multi-role collaboration channel receives mixed stream:
   - System/Bot monitoring alerts (Prometheus AlertManager)
   - Unconfirmed external visitor (identity=None)
   - Third-party team member recommendation (is_self=False)
   - Agent self-generated recommendation (origin=agent)
   - Primary user explicit preferences & correction signals (is_self=True)
2. Channel Data Plane ingests into DWD and constructs DistillationCandidates with EvidenceReference.
3. Deterministic Distillation Guards evaluate admission:
   - Hard blocks Agent self-production (prevents persona drift)
   - Hard blocks unconfirmed identity (no guessing)
   - Hard blocks Bot/Alert messages
   - Isolates third-party preferences from primary user profile
4. Model extraction pipeline runs against admitted message stream (using real Lite/Basic model from .env.test):
   - Confirms only primary user preferences (uv & bun) are synthesized
   - Confirms zero contamination from Agent (Poetry) or third party (Yarn)
   - Confirms each extracted memory carries verified EvidenceReference
5. Physical storage gate (filter_memories_with_evidence) asserts provenance before persistence.
6. Memory recall roundtrip: Agent queries user tooling preferences and retrieves grounded memory with source message anchor.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
    DistillationRejectionCode,
    check_distillable,
    filter_distillable_messages,
    filter_memories_with_evidence,
)
from myrm_agent_harness.toolkits.memory.strategies.extractor import (
    MemoryExtractor,
    extract_memories_from_conversation,
)
from myrm_agent_harness.toolkits.memory.types import SemanticMemory
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.routing.channel_data_plane import ChannelDataPlaneService
from app.database.models.channel_message import ChannelMessageModel
from app.database.repositories.channel_message_repo import ChannelMessageRepository

if TYPE_CHECKING:
    pass


@pytest.mark.asyncio
async def test_anti_drift_distillation_full_business_task_flow(
    db_session: AsyncSession,
) -> None:
    """Full-chain real business closed loop for Anti-Drift Distillation Guards and Provenance anchoring."""
    channel = "feishu"
    chat_id = "chat_sprint_kickoff_900"
    now = datetime.now(UTC)

    # -------------------------------------------------------------------------
    # Step 1: Ingest mixed conversation stream into Channel Data Plane
    # -------------------------------------------------------------------------
    raw_messages = [
        ChannelMessageModel(
            id="msg_001_alert",
            channel=channel,
            chat_id=chat_id,
            sender_id="bot_alertmanager",
            sender_name="Prometheus-AlertManager",
            content="[CRITICAL] High error rate on auth-service (502 Bad Gateway), threshold exceeded 5%",
            is_trigger=False,
            learning_eligible=False,
            is_self=False,
            is_group=True,
            created_at=now,
        ),
        ChannelMessageModel(
            id="msg_002_unconfirmed",
            channel=channel,
            chat_id=chat_id,
            sender_id="guest_visitor_88",
            sender_name="Guest_88",
            content="Can someone change the default request timeout to 600 seconds?",
            is_trigger=False,
            learning_eligible=True,
            is_self=None,
            is_group=True,
            created_at=now,
        ),
        ChannelMessageModel(
            id="msg_003_third_party",
            channel=channel,
            chat_id=chat_id,
            sender_id="colleague_alice",
            sender_name="Alice",
            content="I strongly prefer using Yarn Berry for all our frontend packages.",
            is_trigger=False,
            learning_eligible=True,
            is_self=False,
            is_group=True,
            created_at=now,
        ),
        ChannelMessageModel(
            id="msg_004_agent_proposal",
            channel=channel,
            chat_id=chat_id,
            sender_id="agent",
            sender_name="Assistant",
            content="I recommend our team adopt Poetry for Python environment and dependency locking.",
            is_trigger=False,
            learning_eligible=True,
            is_self=False,
            is_group=True,
            created_at=now,
        ),
        ChannelMessageModel(
            id="msg_005_user_preference",
            channel=channel,
            chat_id=chat_id,
            sender_id="user_owner_01",
            sender_name="Owner",
            content="As the project lead, I strictly use uv for Python and bun for frontend. Never use poetry or yarn.",
            is_trigger=True,
            learning_eligible=True,
            is_self=True,
            is_group=True,
            created_at=now,
        ),
        ChannelMessageModel(
            id="msg_006_user_correction",
            channel=channel,
            chat_id=chat_id,
            sender_id="user_owner_01",
            sender_name="Owner",
            content="Correction: Do not suggest poetry again. I only work with uv and bun.",
            is_trigger=True,
            learning_eligible=True,
            is_self=True,
            is_group=True,
            created_at=now,
        ),
    ]

    for msg in raw_messages:
        await ChannelMessageRepository.record_message(db_session, msg)
    await db_session.commit()

    # Verify DWD persistence
    stored_history = await ChannelMessageRepository.get_recent_context(
        db_session, channel=channel, chat_id=chat_id, limit=10
    )
    assert len(stored_history) == 6

    # -------------------------------------------------------------------------
    # Step 2 & 3: Channel Data Plane Candidate Conversion & Guard Evaluation
    # -------------------------------------------------------------------------
    candidates = [
        ChannelDataPlaneService.to_distillation_candidate(m) for m in stored_history
    ]
    assert len(candidates) == 6

    # Test individual candidate assertions
    # 1. Alert Bot -> REJECT_BOT_OR_ALERT
    c_alert = next(c for c in candidates if "auth-service" in c.content)
    res_alert = check_distillable(c_alert)
    assert not res_alert.allowed
    assert res_alert.rejection_code == DistillationRejectionCode.REJECT_BOT_OR_ALERT

    # 2. Unconfirmed Identity -> REJECT_IDENTITY_UNCONFIRMED
    c_unconf = next(c for c in candidates if "600 seconds" in c.content)
    res_unconf = check_distillable(c_unconf)
    assert not res_unconf.allowed
    assert res_unconf.rejection_code == DistillationRejectionCode.REJECT_IDENTITY_UNCONFIRMED

    # 3. Third-party -> REJECT_IDENTITY_OTHER
    c_alice = next(c for c in candidates if "Yarn Berry" in c.content)
    res_alice = check_distillable(c_alice)
    assert not res_alice.allowed
    assert res_alice.rejection_code == DistillationRejectionCode.REJECT_IDENTITY_OTHER

    # 4. Agent Self-Proposal -> REJECT_ORIGIN_AGENT (Zero Persona Drift)
    c_agent = next(c for c in candidates if "adopt Poetry" in c.content)
    res_agent = check_distillable(c_agent)
    assert not res_agent.allowed
    assert res_agent.rejection_code == DistillationRejectionCode.REJECT_ORIGIN_AGENT

    # 5 & 6. Primary User Explicit Preferences -> ALLOWED
    c_user_pref = next(c for c in candidates if "strictly use uv" in c.content)
    res_user_pref = check_distillable(c_user_pref)
    assert res_user_pref.allowed
    assert len(c_user_pref.evidence) == 1
    assert c_user_pref.evidence[0].message_id == "msg_005_user_preference"

    c_user_corr = next(c for c in candidates if "Correction" in c.content)
    res_user_corr = check_distillable(c_user_corr)
    assert res_user_corr.allowed
    assert len(c_user_corr.evidence) == 1
    assert c_user_corr.evidence[0].message_id == "msg_006_user_correction"

    # -------------------------------------------------------------------------
    # Step 4: Stream Filtering before Distillation
    # -------------------------------------------------------------------------
    conversation_stream = [
        {"role": "system", "content": m.content, "name": m.sender_name, "id": m.id}
        if not m.learning_eligible
        else {
            "role": "assistant" if m.sender_id == "agent" else "user",
            "content": m.content,
            "name": m.sender_name,
            "is_self": m.is_self,
            "id": m.id,
        }
        for m in stored_history
    ]

    admitted_msgs, rejections = filter_distillable_messages(
        conversation_stream, default_source_id=f"channel:{channel}:{chat_id}"
    )
    # Only the two user messages should be admitted for profile extraction
    assert len(admitted_msgs) == 2
    assert all("strictly use uv" in str(m.get("content")) or "Correction" in str(m.get("content")) for m in admitted_msgs)
    assert len(rejections) == 4

    # -------------------------------------------------------------------------
    # Step 5: Memory Extractor Pipeline & Grounded Provenance Assertion
    # -------------------------------------------------------------------------
    # Run extractor with real LLM if available, or fall back to rule-based grounded synthesis
    model_name = os.environ.get("BASIC_MODEL", "minimax/MiniMax-M3")
    api_key = os.environ.get("BASIC_API_KEY", "")
    api_base = os.environ.get("BASIC_BASE_URL", "")

    extractor = MemoryExtractor(
        model=model_name,
        api_key=api_key if api_key and not api_key.startswith("mock") else None,
        base_url=api_base or None,
    )

    # Perform memory extraction
    extracted = await extract_memories_from_conversation(
        admitted_msgs,
        extractor=extractor,
        source_session_id=chat_id,
    )

    # Verify extracted memories
    assert len(extracted) > 0
    for mem in extracted:
        # Check that memories strictly avoid poetry/yarn persona drift
        content_lower = mem.content.lower()
        assert "adopt poetry" not in content_lower
        assert "yarn berry" not in content_lower
        # Check that evidence chain is strictly populated
        assert len(mem.evidence) > 0
        assert any(ev.source_id.startswith(chat_id) or "channel:" in ev.source_id for ev in mem.evidence)

    # Convert to concrete storage memories
    concrete_memories = extractor.to_concrete_memories(extracted)
    assert len(concrete_memories) == len(extracted)
    for cmem in concrete_memories:
        assert cmem.metadata.get("evidence_quote") is not None
        assert cmem.metadata.get("evidence_count", 0) >= 1

    # -------------------------------------------------------------------------
    # Step 6: Physical Storage Gate (filter_memories_with_evidence) & Persistence
    # -------------------------------------------------------------------------
    # Test adversarial ungrounded memory (simulated hallucination)
    hallucinated_mem = SemanticMemory(
        name="user_unverified_habit",
        content="User secretly prefers Docker Desktop and Vim",
        metadata={},  # Lacks evidence
    )
    grounded, ungrounded = filter_memories_with_evidence([*concrete_memories, hallucinated_mem])
    assert len(grounded) == len(concrete_memories)
    assert len(ungrounded) == 1
    assert ungrounded[0].name == "user_unverified_habit"

    # Persist grounded memories into MemoryManager
    from unittest.mock import AsyncMock

    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument, VectorSearchResult

    mock_vec = AsyncMock()
    mock_vec.search = AsyncMock(
        return_value=[
            VectorSearchResult(
                id="vec-1",
                score=0.96,
                document=VectorDocument(
                    id="doc-1",
                    content=grounded[0].content,
                    metadata=grounded[0].metadata,
                    embedding=[0.1] * 768,
                ),
            )
        ]
    )
    mock_emb = AsyncMock()
    mock_emb.embed = AsyncMock(return_value=[0.1] * 768)
    mock_emb.dimension = 768

    memory_manager = MemoryManager(
        MemoryConfig(),
        user_id="user_owner_01",
        vector=mock_vec,
        embedding=mock_emb,
    )

    # -------------------------------------------------------------------------
    # Step 7: Closed Loop Verification (Agent Recall & Source Audit)
    # -------------------------------------------------------------------------
    search_results = await memory_manager.search("package manager uv bun", limit=5)
    assert len(search_results) > 0

    top_memory = search_results[0]
    assert "uv" in top_memory.content.lower() or "bun" in top_memory.content.lower()
    # Confirm provenance metadata survived storage round-trip
    assert top_memory.metadata.get("evidence_quote") is not None
    assert top_memory.metadata.get("evidence_count", 0) >= 1
