"""Real-embedding proof that team identity namespaces isolate memory.

Writes a fact through a manager bound to ``ident:<team-a>`` and verifies it
is recalled in that compartment but invisible from ``ident:<team-b>``.
Uses a real embedding provider and real stores; no mocks, no LLM.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_identity_namespaces_isolate_write_and_recall(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Fact written under one team identity must not leak into another."""
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

    from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding

    tag = uuid.uuid4().hex[:8]
    ns_a = f"ident:e2e-team-a-{tag}"
    ns_b = f"ident:e2e-team-b-{tag}"
    secret = f"代号{tag}"

    embedding_cfg = EmbeddingConfig(
        model=os.environ["EMBEDDING_MODEL"],
        api_key=os.environ["EMBEDDING_API_KEY"],
        api_base=os.environ["EMBEDDING_BASE_URL"],
    )

    async def _manager_for(namespace: str):  # type: ignore[no-untyped-def]
        return await create_memory_manager(
            resolve_context_binding(
                namespaces=[namespace],
                agent_id="e2e-identity-agent",
                channel_id="e2e-channel",
                conversation_id=f"e2e-chat-{tag}",
                task_id=None,
            ),
            embedding_config=embedding_cfg,
            base_path=tmp_path / "memory",
        )

    writer = await _manager_for(ns_a)
    try:
        await writer.add_knowledge(
            f"团队A的秘密代号是{secret}，切勿外传。",
            importance=0.9,
            tags=["e2e-identity"],
        )
    except Exception as exc:
        message = str(exc).lower()
        if any(kw in message for kw in ("402", "insufficient", "quota", "balance", "authentication", "timeout")):
            pytest.skip(f"Embedding provider unavailable (funding/quota): {str(exc)[:160]}")
        raise

    reader_a = await _manager_for(ns_a)
    hits_a = await reader_a.search(f"团队A的秘密代号是什么", limit=5)
    assert any(secret in (hit.content if hasattr(hit, "content") else str(hit)) for hit in hits_a), (
        "fact must be recalled inside its own identity compartment"
    )

    reader_b = await _manager_for(ns_b)
    hits_b = await reader_b.search(f"团队A的秘密代号是什么", limit=5)
    assert all(secret not in (hit.content if hasattr(hit, "content") else str(hit)) for hit in hits_b), (
        "fact must NOT leak into another identity compartment"
    )
