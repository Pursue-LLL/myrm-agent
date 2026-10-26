"""Storage converter round-trips — the payload must give every field back.

The dense and the sparse-mirror read paths share ``doc_to_semantic`` /
``doc_to_episodic``, so a payload field the read converters skip disappears
from listings, searches and tag statistics in *both* modes. These tests pin
the  round-trip for the tag list, which ``semantic_to_doc`` keeps under a
single lowercased ``tags`` key that is excluded from the free-form metadata, and for
the last-use time, which forgetting, the staleness review and the health check read.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.memory._internal.storage_converters import (
    _stamp_access,
    doc_to_episodic,
    doc_to_semantic,
    episodic_to_doc,
    semantic_to_doc,
)
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory
from myrm_agent_harness.toolkits.vector.base import VectorDocument


def _doc(metadata: dict[str, object], *, created_at: datetime | None = None) -> VectorDocument:
    now = created_at or datetime.now(UTC)
    return VectorDocument(
        id="doc-1",
        content="TypeScript strict 模式",
        vector=None,
        metadata=metadata,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
    )


def test_semantic_roundtrip_keeps_tags() -> None:
    memory = SemanticMemory(
        id="sem-1",
        user_id="sandbox_user",
        content="TypeScript strict 模式更安全",
        importance=0.7,
        tags=["CodeStyle", "编辑器"],
    )

    restored = doc_to_semantic(semantic_to_doc(memory))

    assert restored.id == "sem-1"
    assert restored.content == "TypeScript strict 模式更安全"
    assert restored.importance == pytest.approx(0.7)
    assert restored.tags == ["codestyle", "编辑器"]


def test_episodic_roundtrip_keeps_its_own_fields() -> None:
    memory = EpisodicMemory(
        id="epi-1",
        user_id="sandbox_user",
        content="用户在会话中确认了代码风格",
        event_type="decision",
        related_entities=["TypeScript"],
    )

    restored = doc_to_episodic(episodic_to_doc(memory))

    assert restored.id == "epi-1"
    assert restored.event_type == "decision"
    assert restored.related_entities == ["TypeScript"]


def test_semantic_documents_without_tags_read_as_empty() -> None:
    restored = doc_to_semantic(_doc({"user_id": "sandbox_user", "importance": 0.5}))

    assert restored.tags == []


def test_malformed_tag_metadata_reads_as_empty() -> None:
    """Legacy payloads may carry a string or blank entries; never leak non-strings."""
    from_string = doc_to_semantic(_doc({"user_id": "sandbox_user", "tags": "not-a-list"}))
    from_blanks = doc_to_semantic(_doc({"user_id": "sandbox_user", "tags": ["", "  "]}))
    from_scalars = doc_to_semantic(_doc({"user_id": "sandbox_user", "tags": 7}))

    assert from_string.tags == []
    assert from_blanks.tags == []
    assert from_scalars.tags == []


def test_read_converter_keeps_timestamps_and_domain() -> None:
    created = datetime.now(UTC) - timedelta(days=3)
    doc = _doc({"user_id": "sandbox_user", "domain": "user"}, created_at=created)

    restored = doc_to_semantic(doc)

    assert restored.created_at == created
    assert restored.domain.value == "user"


def test_semantic_roundtrip_keeps_last_use() -> None:
    used_at = datetime(2026, 10, 20, 8, 30, tzinfo=UTC)
    memory = SemanticMemory(id="sem-1", user_id="sandbox_user", content="x", access_count=4, last_accessed_at=used_at)

    restored = doc_to_semantic(semantic_to_doc(memory))

    assert restored.access_count == 4
    assert restored.last_accessed_at == used_at
    assert "last_accessed_at" not in restored.metadata


def test_episodic_roundtrip_keeps_last_use() -> None:
    used_at = datetime(2026, 10, 20, 8, 30, tzinfo=UTC)
    memory = EpisodicMemory(id="epi-1", user_id="sandbox_user", content="x", access_count=2, last_accessed_at=used_at)

    restored = doc_to_episodic(episodic_to_doc(memory))

    assert restored.access_count == 2
    assert restored.last_accessed_at == used_at


def test_memory_never_recalled_stores_no_last_use() -> None:
    doc = semantic_to_doc(SemanticMemory(id="sem-1", user_id="sandbox_user", content="x"))

    assert "last_accessed_at" not in doc.metadata
    assert doc_to_semantic(doc).last_accessed_at is None


@pytest.mark.parametrize("raw", ["", "  ", "not-a-date", 17])
def test_malformed_last_use_reads_as_never_recalled(raw: object) -> None:
    doc = semantic_to_doc(SemanticMemory(id="sem-1", user_id="sandbox_user", content="x"))
    doc.metadata["last_accessed_at"] = raw  # type: ignore[assignment]

    assert doc_to_semantic(doc).last_accessed_at is None


def test_stamp_access_records_one_more_use_and_touches_nothing_else() -> None:
    doc = semantic_to_doc(
        SemanticMemory(id="sem-1", user_id="sandbox_user", content="x", access_count=2, importance=0.7)
    )
    doc.vector = [0.1, 0.2]
    others = {k: v for k, v in doc.metadata.items() if k not in ("access_count", "last_accessed_at")}
    updated_at = doc.updated_at
    now = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)

    _stamp_access(doc, now)

    assert doc.metadata["access_count"] == 3
    assert doc.metadata["last_accessed_at"] == now.isoformat()
    assert {k: v for k, v in doc.metadata.items() if k not in ("access_count", "last_accessed_at")} == others
    assert (doc.content, doc.vector, doc.updated_at) == ("x", [0.1, 0.2], updated_at)


def test_stamp_access_counts_a_document_without_a_count_from_zero() -> None:
    doc = _doc({"user_id": "sandbox_user"})

    _stamp_access(doc, datetime(2026, 10, 26, tzinfo=UTC))

    assert doc.metadata["access_count"] == 1
